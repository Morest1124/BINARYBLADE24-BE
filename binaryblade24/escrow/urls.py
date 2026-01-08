"""
Escrow URL Configuration
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EscrowTransactionViewSet,
    InitiateEscrowView,
    ReleaseEscrowView,
    RefundEscrowView,
    EscrowWebhookView
)

# Router for ViewSets
router = DefaultRouter()
router.register(r'transactions', EscrowTransactionViewSet, basename='escrow-transaction')

urlpatterns = [
    # ViewSet routes (includes list, retrieve, etc.)
    path('', include(router.urls)),
    
    # Custom action endpoints
    path('create/', InitiateEscrowView.as_view(), name='escrow-create'),
    path('<int:pk>/release/', ReleaseEscrowView.as_view(), name='escrow-release'),
    path('<int:pk>/refund/', RefundEscrowView.as_view(), name='escrow-refund'),
    
    # Webhook endpoint (no authentication required)
    path('webhook/', EscrowWebhookView.as_view(), name='escrow-webhook'),
]