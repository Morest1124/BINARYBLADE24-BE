from django.db import models
from django.conf import settings
from Project.models import Project
import uuid


class Order(models.Model):
    """
    Represents a complete order/purchase by a client.
    An order can contain multiple items (gigs) with different pricing tiers.
    """
    class OrderStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Payment'
        PAID = 'PAID', 'Paid'
        IN_PROGRESS = 'IN_PROGRESS', 'Work In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REFUNDED = 'REFUNDED', 'Refunded'
    
    order_number = models.CharField(
        max_length=50, 
        unique=True, 
        editable=False,
        help_text="Unique order identifier (e.g., ORD-20250129-ABC123)"
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='orders',
        help_text="Client who placed this order"
    )
    status = models.CharField(
        max_length=20, 
        choices=OrderStatus.choices, 
        default=OrderStatus.PENDING,
        help_text="Current order status",
        db_index=True  # Index for filtering orders by status
    )
    total_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Total order amount (sum of all items)"
    )
    payment = models.ForeignKey(
        'User.Payment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_payment',
        help_text="Associated payment record"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)  # Index for sorting recent orders
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When payment was completed"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'status']),  # User's order dashboard
            models.Index(fields=['status', 'created_at']),  # Recent orders by status
        ]
        
    def __str__(self):
        return f"Order {self.order_number} - {self.client.username}"
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        
        if not is_new:
            try:
                old_instance = Order.objects.get(pk=self.pk)
                old_status = old_instance.status
            except Order.DoesNotExist:
                pass

        if not self.order_number:
            # Generate unique order number: ORD-YYYYMMDD-UUID
            from datetime import datetime
            date_str = datetime.now().strftime('%Y%m%d')
            unique_id = str(uuid.uuid4())[:8].upper()
            self.order_number = f"ORD-{date_str}-{unique_id}"
            
        super().save(*args, **kwargs)
        
        # Broadcast status changes
        if not is_new and old_status != self.status:
            try:
                from notifications.websocket_utils import broadcast_order_update
                # Broadcast to both client and freelancer(s)
                broadcast_order_update(self.client.id, self)
                
                for item in self.items.all():
                    if item.freelancer:
                        broadcast_order_update(item.freelancer.id, self)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to broadcast order update: {e}")
    
    def calculate_total(self):
        """Calculate total from all order items"""
        total = sum(item.final_price for item in self.items.all())
        self.total_amount = total
        self.save()
        return total
    
    def create_escrow_transaction(self):
        """Create escrow transaction via Escrow API when order is paid"""
        from escrow.models import EscrowTransaction
        from escrow.escrow_client import EscrowClient, EscrowAPIException
        from decimal import Decimal
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Check if escrow transaction already exists
        if hasattr(self, 'escrow_transaction'):
            logger.warning(f"Escrow transaction already exists for order {self.order_number}")
            return self.escrow_transaction
        
        # Get freelancer from first order item
        first_item = self.items.select_related('freelancer', 'project').first()
        if not first_item:
            logger.error(f"Cannot create escrow for order {self.order_number}: No items found")
            return None
        
        try:
            # Initialize Escrow API client
            escrow_client = EscrowClient()
            
            # Create escrow transaction via API
            api_response = escrow_client.create_transaction(
                order_id=self.order_number,
                client_email=self.client.email,
                freelancer_email=first_item.freelancer.email,
                total_amount=self.total_amount,
                project_title=first_item.project.title,
                currency='USD'
            )
            
            # Calculate fees
            fees = escrow_client.calculate_fees(self.total_amount)
            
            # Create local escrow transaction record
            escrow_transaction = EscrowTransaction.objects.create(
                order=self,
                client=self.client,
                freelancer=first_item.freelancer,
                escrow_id=api_response['id'],
                total_amount=self.total_amount,
                platform_fee=fees['platform_fee'],
                freelancer_amount=fees['freelancer_amount'],
                currency='USD',
                status=EscrowTransaction.TransactionStatus.PENDING,
                escrow_response=api_response
            )
            
            logger.info(f"Escrow transaction created: {escrow_transaction.escrow_id} for order {self.order_number}")
            return escrow_transaction
            
        except EscrowAPIException as e:
            logger.error(f"Failed to create escrow for order {self.order_number}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error creating escrow for order {self.order_number}: {e}")
            return None
    
    def create_escrow(self):
        """Legacy method - redirects to new escrow API integration"""
        return self.create_escrow_transaction()
    
    def approve_and_release_payment(self):
        """Client approves work and releases payment from escrow"""
        # Use new escrow transaction system if available
        if hasattr(self, 'escrow_transaction'):
            from escrow.escrow_client import EscrowClient, EscrowAPIException
            import logging
            
            logger = logging.getLogger(__name__)
            
            if self.escrow_transaction.is_active:
                try:
                    # Call Escrow API to accept/release funds
                    escrow_client = EscrowClient()
                    escrow_client.accept_transaction(self.escrow_transaction.escrow_id)
                    
                    # Update local status
                    self.escrow_transaction.mark_as_disbursed()
                    
                    # Update order status
                    self.status = self.OrderStatus.COMPLETED
                    self.save()
                    
                    logger.info(f"Payment released for order {self.order_number}")
                    return True
                    
                except EscrowAPIException as e:
                    logger.error(f"Failed to release payment for order {self.order_number}: {e}")
                    return False
        
        # Fallback to legacy escrow system
        elif hasattr(self, 'escrow'):
            if self.status == self.OrderStatus.PAID:
                if self.escrow.release_to_freelancer():
                    self.status = self.OrderStatus.COMPLETED
                    self.save()
                    return True
        
        return False

    def cancel_order(self, user):
        """
        Cancel the order.
        If paid, refund to client.
        Only client or freelancer can cancel.
        """
        # Check permissions (though view should handle this too)
        is_client = user == self.client
        is_freelancer = self.items.filter(freelancer=user).exists()
        
        if not (is_client or is_freelancer):
            return False, "Permission denied"

        if self.status == self.OrderStatus.COMPLETED:
            return False, "Cannot cancel a completed order"
            
        if self.status == self.OrderStatus.CANCELLED:
            return False, "Order is already cancelled"

        # Handle Refund if Paid
        if self.status in [self.OrderStatus.PAID, self.OrderStatus.IN_PROGRESS]:
            if hasattr(self, 'escrow') and self.escrow.status == 'HELD':
                if self.escrow.refund_to_client():
                    self.status = self.OrderStatus.REFUNDED
                    self.save()
                    return True, "Order cancelled and funds refunded to client"
                else:
                    return False, "Failed to refund escrow"
            else:
                # Paid but no escrow? Should not happen in new system, but handle gracefully
                self.status = self.OrderStatus.CANCELLED
                self.save()
                return True, "Order cancelled (Manual refund may be required)"

        # Handle Pending Order
        if self.status == self.OrderStatus.PENDING:
            self.status = self.OrderStatus.CANCELLED
            self.save()
            return True, "Order cancelled successfully"
            
        return False, "Invalid order status for cancellation"


class OrderItem(models.Model):
    """
    Represents a single item (gig purchase) within an order.
    Stores the selected pricing tier and calculated price.
    """
    class TierChoice(models.TextChoices):
        SIMPLE = 'SIMPLE', 'Simple Package'
        MEDIUM = 'MEDIUM', 'Medium Package'
        EXPERT = 'EXPERT', 'Expert Package'
    
    order = models.ForeignKey(
        Order, 
        on_delete=models.CASCADE, 
        related_name='items',
        help_text="Parent order"
    )
    project = models.ForeignKey(
        Project, 
        on_delete=models.PROTECT,
        help_text="Gig being purchased"
    )
    tier = models.CharField(
        max_length=10, 
        choices=TierChoice.choices,
        help_text="Selected pricing tier",
        db_index=True  # Index for filtering by package tier
    )
    base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Original gig price (from project.budget)"
    )
    tier_multiplier = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        help_text="Pricing multiplier (1.0, 1.5, 2.0)"
    )
    final_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Calculated price (base_price × tier_multiplier)"
    )
    freelancer = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name='received_orders',
        help_text="Freelancer who will fulfill this order"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['order', 'freelancer']),  # Tracking freelancer earnings
        ]
        
    def __str__(self):
        return f"{self.project.title} - {self.tier} ({self.order.order_number})"
    
    def save(self, *args, **kwargs):
        # Auto-calculate final price based on tier
        if not self.final_price or not self.tier_multiplier:
            from decimal import Decimal
            tier_multipliers = {
                self.TierChoice.SIMPLE: Decimal('1.0'),
                self.TierChoice.MEDIUM: Decimal('1.5'),
                self.TierChoice.EXPERT: Decimal('2.0')
            }
            self.tier_multiplier = tier_multipliers.get(self.tier, Decimal('1.0'))
            self.final_price = self.base_price * self.tier_multiplier
        
        super().save(*args, **kwargs)
        
        # Update parent order total
        if self.order_id:
            self.order.calculate_total()
    
    @property
    def tier_features(self):
        """Return features based on selected tier"""
        features = {
            self.TierChoice.SIMPLE: [
                'Standard delivery time',
                'Basic features',
                '1 revision included'
            ],
            self.TierChoice.MEDIUM: [
                'Priority delivery',
                'Advanced features',
                '3 revisions included',
                'Priority support'
            ],
            self.TierChoice.EXPERT: [
                'Express delivery',
                'Premium features',
                'Unlimited revisions',
                '24/7 priority support',
                'Source files included'
            ]
        }
        return features.get(self.tier, [])


class Escrow(models.Model):
    """
    Holds payment funds until work is approved by client.
    Implements escrow payment system similar to Fiverr/Upwork.
    """
    class EscrowStatus(models.TextChoices):
        HELD = 'HELD', 'Funds Held in Escrow'
        RELEASED = 'RELEASED', 'Released to Freelancer'
        REFUNDED = 'REFUNDED', 'Refunded to Client'
    
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name='escrow',
        help_text="Order associated with this escrow"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount held in escrow"
    )
    status = models.CharField(
        max_length=20,
        choices=EscrowStatus.choices,
        default=EscrowStatus.HELD,
        help_text="Current escrow status",
        db_index=True  # Index for tracking escrow state
    )
    held_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When funds were placed in escrow"
    )
    released_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When funds were released to freelancer"
    )
    refunded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When funds were refunded to client"
    )
    
    class Meta:
        verbose_name = "Escrow"
        verbose_name_plural = "Escrows"
        ordering = ['-held_at']
        indexes = [
            models.Index(fields=['status', 'held_at']),  # Finding held/pending escrows
        ]
    
    def __str__(self):
        return f"Escrow for {self.order.order_number} - {self.get_status_display()}"
    
    def release_to_freelancer(self):
        """Release escrow funds to freelancer(s)"""
        if self.status == self.EscrowStatus.HELD:
            from django.utils import timezone
            
            # Release funds to each freelancer in the order
            for item in self.order.items.all():
                # In a real system, this would transfer to freelancer's bank account
                # For now, we'll just mark it as released
                pass
            
            self.status = self.EscrowStatus.RELEASED
            self.released_at = timezone.now()
            self.save()
            return True
        return False
    
    def refund_to_client(self):
        """Refund escrow funds to client"""
        if self.status == self.EscrowStatus.HELD:
            from django.utils import timezone
            
            # In a real system, this would transfer back to client's account
            self.status = self.EscrowStatus.REFUNDED
            self.refunded_at = timezone.now()
            self.save()
            return True
        return False
