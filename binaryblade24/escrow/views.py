"""
Escrow API Views - Handle escrow transaction operations
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import logging
import json

from .models import EscrowTransaction, EscrowWebhookLog
from .serializers import (
    EscrowTransactionSerializer,
    CreateEscrowSerializer,
    UpdateEscrowStatusSerializer,
    RefundEscrowSerializer,
    ReleaseEscrowSerializer,
    EscrowWebhookSerializer,
    EscrowSummarySerializer
)
from .escrow_client import EscrowClient, EscrowAPIException
from Order.models import Order

logger = logging.getLogger(__name__)


class EscrowTransactionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing escrow transactions
    
    list: Get all escrow transactions for authenticated user
    retrieve: Get specific escrow transaction details
    create: Create a new escrow transaction for an order
    """
    
    serializer_class = EscrowTransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter escrow transactions based on user role"""
        user = self.request.user
        
        # Users can see escrows where they are client or freelancer
        return EscrowTransaction.objects.filter(
            Q(client=user) | Q(freelancer=user)
        ).select_related('client', 'freelancer', 'order').order_by('-created_at')
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get escrow transaction summary for the authenticated user"""
        user = request.user
        
        # Get transactions where user is involved
        transactions = EscrowTransaction.objects.filter(
            Q(client=user) | Q(freelancer=user)
        )
        
        # As freelancer
        freelancer_transactions = transactions.filter(freelancer=user)
        freelancer_stats = freelancer_transactions.aggregate(
            total_earned=Sum('freelancer_amount'),
            completed=Count('id', filter=Q(status=EscrowTransaction.TransactionStatus.DISBURSED))
        )
        
        # As client
        client_transactions = transactions.filter(client=user)
        client_stats = client_transactions.aggregate(
            total_spent=Sum('total_amount'),
            completed=Count('id', filter=Q(status=EscrowTransaction.TransactionStatus.DISBURSED))
        )
        
        data = {
            'total_escrows': transactions.count(),
            'total_amount': transactions.aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
            'platform_fees_earned': transactions.aggregate(Sum('platform_fee'))['platform_fee__sum'] or 0,
            'freelancer_payouts': transactions.aggregate(Sum('freelancer_amount'))['freelancer_amount__sum'] or 0,
            'pending_count': transactions.filter(status=EscrowTransaction.TransactionStatus.PENDING).count(),
            'funded_count': transactions.filter(status=EscrowTransaction.TransactionStatus.FUNDED).count(),
            'disbursed_count': transactions.filter(status=EscrowTransaction.TransactionStatus.DISBURSED).count(),
            'refunded_count': transactions.filter(status=EscrowTransaction.TransactionStatus.REFUNDED).count(),
            'as_freelancer': {
                'total_earned': freelancer_stats['total_earned'] or 0,
                'completed_jobs': freelancer_stats['completed']
            },
            'as_client': {
                'total_spent': client_stats['total_spent'] or 0,
                'completed_orders': client_stats['completed']
            }
        }
        
        serializer = EscrowSummarySerializer(data)
        return Response(serializer.data)


class InitiateEscrowView(APIView):
    """
    Create escrow transaction when order is paid
    POST /api/escrow/create/
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Create a new escrow transaction for a paid order"""
        serializer = CreateEscrowSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        order_id = serializer.validated_data['order_id']
        currency = serializer.validated_data.get('currency', 'USD')
        inspection_period = serializer.validated_data.get('inspection_period', 259200)
        
        try:
            order = Order.objects.select_related('client').get(id=order_id)
            
            # Verify user is the client
            if order.client != request.user:
                return Response(
                    {'error': 'Only the order client can create escrow'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get freelancer from first order item
            # Assuming single freelancer per order for now
            first_item = order.items.select_related('freelancer', 'project').first()
            if not first_item:
                return Response(
                    {'error': 'Order has no items'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            freelancer = first_item.freelancer
            project_title = first_item.project.title
            
            # Initialize Escrow API client
            escrow_client = EscrowClient()
            
            # Create escrow transaction via API
            api_response = escrow_client.create_transaction(
                order_id=order.order_number,
                client_email=order.client.email,
                freelancer_email=freelancer.email,
                total_amount=order.total_amount,
                project_title=project_title,
                currency=currency,
                inspection_period=inspection_period
            )
            
            # Calculate fees
            fees = escrow_client.calculate_fees(order.total_amount)
            
            # Create local escrow transaction record
            escrow_transaction = EscrowTransaction.objects.create(
                order=order,
                client=order.client,
                freelancer=freelancer,
                escrow_id=api_response['id'],
                total_amount=order.total_amount,
                platform_fee=fees['platform_fee'],
                freelancer_amount=fees['freelancer_amount'],
                currency=currency.upper(),
                status=EscrowTransaction.TransactionStatus.PENDING,
                escrow_response=api_response
            )
            
            # Update order status
            order.status = Order.OrderStatus.IN_PROGRESS
            order.save()
            
            logger.info(f"Escrow transaction created: {escrow_transaction.escrow_id} for order {order.order_number}")
            
            response_serializer = EscrowTransactionSerializer(escrow_transaction)
            return Response({
                'escrow_transaction': response_serializer.data,
                'payment_url': f"https://www.escrow-sandbox.com/checkout/{api_response['id']}",
                'message': 'Escrow transaction created successfully'
            }, status=status.HTTP_201_CREATED)
            
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except EscrowAPIException as e:
            logger.error(f"Escrow API error: {e}")
            return Response(
                {'error': f'Failed to create escrow transaction: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.exception(f"Unexpected error creating escrow: {e}")
            return Response(
                {'error': 'An unexpected error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReleaseEscrowView(APIView):
    """
    Release escrow to freelancer when client approves work
    POST /api/escrow/<id>/release/
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """Release escrow funds to freelancer"""
        serializer = ReleaseEscrowSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            escrow_transaction = EscrowTransaction.objects.select_related(
                'order', 'client', 'freelancer'
            ).get(pk=pk)
            
            # Verify user is the client
            if escrow_transaction.client != request.user:
                return Response(
                    {'error': 'Only the client can release escrow funds'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Verify escrow can be released
            if not escrow_transaction.is_active:
                return Response(
                    {'error': f'Cannot release escrow in {escrow_transaction.get_status_display()} status'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Call Escrow API to accept transaction
            escrow_client = EscrowClient()
            api_response = escrow_client.accept_transaction(escrow_transaction.escrow_id)
            
            # Update local status
            escrow_transaction.mark_as_disbursed()
            
            # Update order status
            order = escrow_transaction.order
            order.status = Order.OrderStatus.COMPLETED
            order.save()
            
            logger.info(f"Escrow {escrow_transaction.escrow_id} released to freelancer {escrow_transaction.freelancer.email}")
            
            response_serializer = EscrowTransactionSerializer(escrow_transaction)
            return Response({
                'escrow_transaction': response_serializer.data,
                'message': 'Payment released to freelancer successfully',
                'freelancer_received': float(escrow_transaction.freelancer_amount)
            }, status=status.HTTP_200_OK)
            
        except EscrowTransaction.DoesNotExist:
            return Response(
                {'error': 'Escrow transaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except EscrowAPIException as e:
            logger.error(f"Escrow API error: {e}")
            return Response(
                {'error': f'Failed to release escrow: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.exception(f"Unexpected error releasing escrow: {e}")
            return Response(
                {'error': 'An unexpected error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RefundEscrowView(APIView):
    """
    Refund escrow to client when order is cancelled
    POST /api/escrow/<id>/refund/
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """Refund escrow to client"""
        serializer = RefundEscrowSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            escrow_transaction = EscrowTransaction.objects.select_related(
                'order', 'client', 'freelancer'
            ).get(pk=pk)
            
            # Verify user is client or freelancer
            if request.user not in [escrow_transaction.client, escrow_transaction.freelancer]:
                return Response(
                    {'error': 'Only the client or freelancer can request refund'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Verify escrow can be refunded
            if escrow_transaction.status == EscrowTransaction.TransactionStatus.DISBURSED:
                return Response(
                    {'error': 'Cannot refund already disbursed escrow'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Call Escrow API to cancel transaction
            escrow_client = EscrowClient()
            api_response = escrow_client.cancel_transaction(escrow_transaction.escrow_id)
            
            # Update local status
            escrow_transaction.mark_as_refunded()
            escrow_transaction.notes += f"\nRefund requested by {request.user.email}: {serializer.validated_data['reason']}"
            escrow_transaction.save()
            
            # Update order status
            order = escrow_transaction.order
            order.status = Order.OrderStatus.REFUNDED
            order.save()
            
            logger.info(f"Escrow {escrow_transaction.escrow_id} refunded to client {escrow_transaction.client.email}")
            
            response_serializer = EscrowTransactionSerializer(escrow_transaction)
            return Response({
                'escrow_transaction': response_serializer.data,
                'message': 'Refund initiated successfully',
                'refund_amount': float(escrow_transaction.total_amount)
            }, status=status.HTTP_200_OK)
            
        except EscrowTransaction.DoesNotExist:
            return Response(
                {'error': 'Escrow transaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except EscrowAPIException as e:
            logger.error(f"Escrow API error: {e}")
            return Response(
                {'error': f'Failed to refund escrow: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.exception(f"Unexpected error refunding escrow: {e}")
            return Response(
                {'error': 'An unexpected error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class EscrowWebhookView(APIView):
    """
    Handle webhooks from Escrow.com
    POST /api/escrow/webhook/
    """
    
    permission_classes = []  # Webhooks don't use session auth
    
    def post(self, request):
        """Process webhook from Escrow API"""
        
        # Get signature from header
        signature = request.headers.get('X-Escrow-Signature', '')
        
        # Verify signature
        escrow_client = EscrowClient()
        payload_bytes = request.body
        
        signature_valid = escrow_client.verify_webhook_signature(payload_bytes, signature)
        
        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
        
        event_type = payload.get('event_type', 'unknown')
        transaction_id = payload.get('transaction', {}).get('id')
        
        # Log webhook
        webhook_log = EscrowWebhookLog.objects.create(
            event_type=event_type,
            payload=payload,
            signature=signature,
            signature_valid=signature_valid
        )
        
        # Only process if signature is valid
        if not signature_valid:
            logger.warning(f"Invalid webhook signature for event {event_type}")
            webhook_log.processing_error = "Invalid signature"
            webhook_log.save()
            return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Find associated escrow transaction
        try:
            if transaction_id:
                escrow_transaction = EscrowTransaction.objects.get(escrow_id=transaction_id)
                webhook_log.escrow_transaction = escrow_transaction
                webhook_log.save()
                
                # Process event based on type
                self._process_webhook_event(escrow_transaction, event_type, payload)
                
                webhook_log.processed = True
                webhook_log.processed_at = timezone.now()
                webhook_log.save()
                
        except EscrowTransaction.DoesNotExist:
            logger.warning(f"Escrow transaction {transaction_id} not found for webhook")
            webhook_log.processing_error = f"Transaction {transaction_id} not found"
            webhook_log.save()
        except Exception as e:
            logger.exception(f"Error processing webhook: {e}")
            webhook_log.processing_error = str(e)
            webhook_log.save()
            return Response({'error': 'Processing failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'status': 'received'}, status=status.HTTP_200_OK)
    
    def _process_webhook_event(self, escrow_transaction, event_type, payload):
        """Process specific webhook event types"""
        
        if event_type == 'transaction.funded':
            escrow_transaction.mark_as_funded()
            logger.info(f"Escrow {escrow_transaction.escrow_id} funded")
            
        elif event_type == 'transaction.shipped':
            escrow_transaction.mark_as_shipped()
            logger.info(f"Escrow {escrow_transaction.escrow_id} marked as shipped")
            
        elif event_type == 'transaction.disbursed':
            escrow_transaction.mark_as_disbursed()
            logger.info(f"Escrow {escrow_transaction.escrow_id} disbursed")
            
        elif event_type == 'transaction.cancelled':
            escrow_transaction.mark_as_cancelled()
            logger.info(f"Escrow {escrow_transaction.escrow_id} cancelled")
            
        elif event_type == 'transaction.refunded':
            escrow_transaction.mark_as_refunded()
            logger.info(f"Escrow {escrow_transaction.escrow_id} refunded")
            
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")