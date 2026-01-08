"""
Escrow Models - Track external escrow transactions
"""

from django.db import models
from django.conf import settings
from decimal import Decimal
from django.utils import timezone


class EscrowTransaction(models.Model):
    """
    Tracks escrow transactions from Escrow.com API
    Links orders with external escrow service for three-way payment
    """
    
    class TransactionStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending - Awaiting Payment'
        FUNDED = 'FUNDED', 'Funded - Payment Received'
        SHIPPING = 'SHIPPING', 'Work Delivered - Awaiting Approval'
        DISBURSED = 'DISBURSED', 'Disbursed - Funds Released'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REFUNDED = 'REFUNDED', 'Refunded to Client'
        DISPUTED = 'DISPUTED', 'Under Dispute'
    
    # Internal References
    order = models.OneToOneField(
        'Order.Order',
        on_delete=models.PROTECT,
        related_name='escrow_transaction',
        help_text="Associated order"
    )
    
    # Party References
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='client_escrow_transactions',
        help_text="Client who is paying"
    )
    
    freelancer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='freelancer_escrow_transactions',
        help_text="Freelancer who will receive payment"
    )
    
    # External Escrow API References
    escrow_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Escrow.com transaction ID",
        db_index=True
    )
    
    # Financial Details
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Total transaction amount"
    )
    
    platform_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Platform commission (20%)"
    )
    
    freelancer_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Freelancer payout (80%)"
    )
    
    currency = models.CharField(
        max_length=3,
        default='USD',
        help_text="Currency code (ISO 4217)"
    )
    
    # Status Tracking
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
        db_index=True
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    funded_at = models.DateTimeField(null=True, blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    
    # Additional Data
    escrow_response = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full response from Escrow API"
    )
    
    notes = models.TextField(
        blank=True,
        help_text="Internal notes about this transaction"
    )
    
    class Meta:
        verbose_name = "Escrow Transaction"
        verbose_name_plural = "Escrow Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['freelancer', 'status']),
            models.Index(fields=['escrow_id']),
        ]
    
    def __str__(self):
        return f"Escrow {self.escrow_id} - Order {self.order.order_number} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        """Calculate fees before saving if not set"""
        if not self.platform_fee or not self.freelancer_amount:
            from django.conf import settings
            platform_percentage = getattr(settings, 'PLATFORM_FEE_PERCENTAGE', Decimal('0.20'))
            freelancer_percentage = getattr(settings, 'FREELANCER_PAYOUT_PERCENTAGE', Decimal('0.80'))
            
            self.platform_fee = (self.total_amount * platform_percentage).quantize(Decimal('0.01'))
            self.freelancer_amount = (self.total_amount * freelancer_percentage).quantize(Decimal('0.01'))
        
        super().save(*args, **kwargs)
    
    def mark_as_funded(self):
        """Mark transaction as funded when payment is received"""
        if self.status == self.TransactionStatus.PENDING:
            self.status = self.TransactionStatus.FUNDED
            self.funded_at = timezone.now()
            self.save()
    
    def mark_as_shipped(self):
        """Mark as work delivered (awaiting client approval)"""
        if self.status == self.TransactionStatus.FUNDED:
            self.status = self.TransactionStatus.SHIPPING
            self.save()
    
    def mark_as_disbursed(self):
        """Mark as disbursed when funds are released to freelancer and platform"""
        if self.status in [self.TransactionStatus.FUNDED, self.TransactionStatus.SHIPPING]:
            self.status = self.TransactionStatus.DISBURSED
            self.disbursed_at = timezone.now()
            self.save()
            
            # Update freelancer wallet balance
            if hasattr(self.freelancer, 'profile'):
                profile = self.freelancer.profile
                profile.wallet_balance += self.freelancer_amount
                profile.save()
    
    def mark_as_refunded(self):
        """Mark as refunded when cancelled and money returned to client"""
        if self.status in [self.TransactionStatus.PENDING, self.TransactionStatus.FUNDED]:
            self.status = self.TransactionStatus.REFUNDED
            self.save()
    
    def mark_as_cancelled(self):
        """Mark as cancelled"""
        if self.status not in [self.TransactionStatus.DISBURSED, self.TransactionStatus.REFUNDED]:
            self.status = self.TransactionStatus.CANCELLED
            self.save()
    
    @property
    def is_active(self):
        """Returns True if transaction can still be modified"""
        return self.status in [
            self.TransactionStatus.PENDING,
            self.TransactionStatus.FUNDED,
            self.TransactionStatus.SHIPPING
        ]
    
    @property
    def is_completed(self):
        """Returns True if funds have been disbursed"""
        return self.status == self.TransactionStatus.DISBURSED
    
    @property
    def platform_fee_percentage(self):
        """Calculate platform fee percentage"""
        if self.total_amount > 0:
            return (self.platform_fee / self.total_amount) * 100
        return 0


class EscrowWebhookLog(models.Model):
    """
    Logs webhooks received from Escrow.com for debugging and audit
    """
    
    escrow_transaction = models.ForeignKey(
        EscrowTransaction,
        on_delete=models.CASCADE,
        related_name='webhook_logs',
        null=True,
        blank=True,
        help_text="Associated escrow transaction (if identifiable)"
    )
    
    event_type = models.CharField(
        max_length=100,
        help_text="Webhook event type"
    )
    
    payload = models.JSONField(
        help_text="Full webhook payload"
    )
    
    signature = models.CharField(
        max_length=255,
        blank=True,
        help_text="Webhook signature for verification"
    )
    
    signature_valid = models.BooleanField(
        default=False,
        help_text="Whether signature verification passed"
    )
    
    processed = models.BooleanField(
        default=False,
        help_text="Whether this webhook has been processed"
    )
    
    processing_error = models.TextField(
        blank=True,
        help_text="Error message if processing failed"
    )
    
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Escrow Webhook Log"
        verbose_name_plural = "Escrow Webhook Logs"
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['event_type', 'received_at']),
            models.Index(fields=['processed', 'received_at']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.received_at.strftime('%Y-%m-%d %H:%M:%S')}"