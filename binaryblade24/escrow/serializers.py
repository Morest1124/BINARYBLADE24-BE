"""
Escrow Serializers - API serialization for escrow transactions
"""

from rest_framework import serializers
from .models import EscrowTransaction, EscrowWebhookLog
from Order.models import Order
from decimal import Decimal


class EscrowTransactionSerializer(serializers.ModelSerializer):
    """Serializer for escrow transaction details"""
    
    client_email = serializers.EmailField(source='client.email', read_only=True)
    client_name = serializers.CharField(source='client.get_full_name', read_only=True)
    freelancer_email = serializers.EmailField(source='freelancer.email', read_only=True)
    freelancer_name = serializers.CharField(source='freelancer.get_full_name', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    project_title = serializers.CharField(source='order.items.first.project.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    platform_fee_percentage_display = serializers.DecimalField(
        source='platform_fee_percentage',
        max_digits=5,
        decimal_places=2,
        read_only=True
    )
    
    class Meta:
        model = EscrowTransaction
        fields = [
            'id',
            'order',
            'order_number',
            'project_title',
            'client',
            'client_email',
            'client_name',
            'freelancer',
            'freelancer_email',
            'freelancer_name',
            'escrow_id',
            'total_amount',
            'platform_fee',
            'freelancer_amount',
            'platform_fee_percentage_display',
            'currency',
            'status',
            'status_display',
            'created_at',
            'updated_at',
            'funded_at',
            'disbursed_at',
            'notes',
        ]
        read_only_fields = [
            'id',
            'escrow_id',
            'platform_fee',
            'freelancer_amount',
            'created_at',
            'updated_at',
            'funded_at',
            'disbursed_at',
        ]


class CreateEscrowSerializer(serializers.Serializer):
    """Serializer for creating a new escrow transaction"""
    
    order_id = serializers.IntegerField(
        help_text="Order ID to create escrow for"
    )
    
    currency = serializers.CharField(
        max_length=3,
        default='USD',
        help_text="Currency code (USD, EUR, GBP, etc.)"
    )
    
    inspection_period = serializers.IntegerField(
        default=259200,  # 3 days
        help_text="Inspection period in seconds (default: 3 days)"
    )
    
    def validate_order_id(self, value):
        """Validate that order exists and doesn't have escrow yet"""
        try:
            order = Order.objects.get(id=value)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found")
        
        # Check if escrow already exists
        if hasattr(order, 'escrow_transaction'):
            raise serializers.ValidationError("Escrow transaction already exists for this order")
        
        # Check if order is paid
        if order.status != Order.OrderStatus.PAID:
            raise serializers.ValidationError("Order must be in PAID status to create escrow")
        
        return value


class UpdateEscrowStatusSerializer(serializers.Serializer):
    """Serializer for updating escrow transaction status"""
    
    action = serializers.ChoiceField(
        choices=['agree', 'ship', 'receive', 'accept', 'reject', 'cancel'],
        help_text="Action to perform on the escrow transaction"
    )
    
    # Optional fields for specific actions
    rejection_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Reason for rejection (required if action=reject)"
    )
    
    carrier = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Shipping carrier (optional for action=ship)"
    )
    
    tracking_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Tracking ID (optional for action=ship)"
    )
    
    def validate(self, data):
        """Validate action-specific fields"""
        action = data.get('action')
        
        # Reject action should have a reason
        if action == 'reject' and not data.get('rejection_reason'):
            raise serializers.ValidationError({
                'rejection_reason': 'Rejection reason is required when rejecting work'
            })
        
        return data


class RefundEscrowSerializer(serializers.Serializer):
    """Serializer for refunding an escrow transaction"""
    
    reason = serializers.CharField(
        max_length=500,
        help_text="Reason for refund"
    )
    
    confirm = serializers.BooleanField(
        help_text="Confirmation to proceed with refund"
    )
    
    def validate_confirm(self, value):
        """Ensure confirmation is True"""
        if not value:
            raise serializers.ValidationError("You must confirm the refund action")
        return value


class ReleaseEscrowSerializer(serializers.Serializer):
    """Serializer for releasing escrow to freelancer"""
    
    confirm = serializers.BooleanField(
        help_text="Confirmation to release payment"
    )
    
    feedback = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional feedback for the freelancer"
    )
    
    rating = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=5,
        help_text="Optional rating (1-5 stars)"
    )
    
    def validate_confirm(self, value):
        """Ensure confirmation is True"""
        if not value:
            raise serializers.ValidationError("You must confirm payment release")
        return value


class EscrowWebhookSerializer(serializers.ModelSerializer):
    """Serializer for webhook logs"""
    
    escrow_id = serializers.CharField(source='escrow_transaction.escrow_id', read_only=True)
    
    class Meta:
        model = EscrowWebhookLog
        fields = [
            'id',
            'escrow_transaction',
            'escrow_id',
            'event_type',
            'payload',
            'signature_valid',
            'processed',
            'processing_error',
            'received_at',
            'processed_at',
        ]
        read_only_fields = ['id', 'received_at', 'processed_at']


class EscrowSummarySerializer(serializers.Serializer):
    """Serializer for escrow transaction summary/statistics"""
    
    total_escrows = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    platform_fees_earned = serializers.DecimalField(max_digits=12, decimal_places=2)
    freelancer_payouts = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_count = serializers.IntegerField()
    funded_count = serializers.IntegerField()
    disbursed_count = serializers.IntegerField()
    refunded_count = serializers.IntegerField()