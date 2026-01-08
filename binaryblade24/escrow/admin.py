"""
Escrow Admin Configuration
"""

from django.contrib import admin
from .models import EscrowTransaction, EscrowWebhookLog


@admin.register(EscrowTransaction)
class EscrowTransactionAdmin(admin.ModelAdmin):
    """Admin interface for escrow transactions"""
    
    list_display = [
        'escrow_id',
        'order',
        'client',
        'freelancer',
        'total_amount',
        'platform_fee',
        'freelancer_amount',
        'status',
        'created_at'
    ]
    
    list_filter = [
        'status',
        'currency',
        'created_at',
        'funded_at',
        'disbursed_at'
    ]
    
    search_fields = [
        'escrow_id',
        'order__order_number',
        'client__email',
        'client__username',
        'freelancer__email',
        'freelancer__username'
    ]
    
    readonly_fields = [
        'escrow_id',
        'platform_fee',
        'freelancer_amount',
        'created_at',
        'updated_at',
        'funded_at',
        'disbursed_at',
        'escrow_response',
        'platform_fee_percentage'
    ]
    
    fieldsets = (
        ('Transaction Details', {
            'fields': (
                'escrow_id',
                'order',
                'status'
            )
        }),
        ('Parties', {
            'fields': (
                'client',
                'freelancer'
            )
        }),
        ('Financial Details', {
            'fields': (
                'total_amount',
                'platform_fee',
                'freelancer_amount',
                'platform_fee_percentage',
                'currency'
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
                'funded_at',
                'disbursed_at'
            )
        }),
        ('Additional Information', {
            'fields': (
                'notes',
                'escrow_response'
            ),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('client', 'freelancer', 'order')
    
    def has_add_permission(self, request):
        """Prevent manual creation through admin"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion through admin"""
        return False


@admin.register(EscrowWebhookLog)
class EscrowWebhookLogAdmin(admin.ModelAdmin):
    """Admin interface for webhook logs"""
    
    list_display = [
        'id',
        'event_type',
        'escrow_transaction',
        'signature_valid',
        'processed',
        'received_at'
    ]
    
    list_filter = [
        'event_type',
        'signature_valid',
        'processed',
        'received_at'
    ]
    
    search_fields = [
        'event_type',
        'escrow_transaction__escrow_id'
    ]
    
    readonly_fields = [
        'escrow_transaction',
        'event_type',
        'payload',
        'signature',
        'signature_valid',
        'received_at',
        'processed_at'
    ]
    
    fieldsets = (
        ('Webhook Details', {
            'fields': (
                'event_type',
                'escrow_transaction',
                'received_at'
            )
        }),
        ('Processing Status', {
            'fields': (
                'processed',
                'processed_at',
                'processing_error'
            )
        }),
        ('Security', {
            'fields': (
                'signature',
                'signature_valid'
            )
        }),
        ('Payload', {
            'fields': ('payload',),
            'classes': ('collapse',)
        })
    )
    
    def has_add_permission(self, request):
        """Prevent manual creation"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Read-only access"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion of old logs"""
        return request.user.is_superuser
