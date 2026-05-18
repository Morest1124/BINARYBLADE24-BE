from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from datetime import timedelta
from .models import Order
from .serializers import OrderSerializer
import logging
import re

logger = logging.getLogger(__name__)

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Clients see their own orders
        # Freelancers see orders they are fulfilling (via items)
        user = self.request.user
        
        # Use Q objects to combine queries instead of queryset union
        from django.db.models import Q
        
        # Return orders where user is either the client OR a freelancer for any item
        return Order.objects.filter(
            Q(client=user) | Q(items__freelancer=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(client=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """
        Mark order as paid and create escrow transaction.
        This triggers the escrow creation and sets order to IN_PROGRESS.
        In production, this would be called by payment gateway webhook.
        """
        order = self.get_object()
        
        if order.status != Order.OrderStatus.PENDING:
            return Response(
                {'error': f'Order is not pending (current status: {order.status})'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark order as paid
        order.paid_at = timezone.now()
        order.save()
        
        # Create escrow transaction to hold funds
        escrow_transaction = order.create_escrow_transaction()
        
        if escrow_transaction:
            # Set order to IN_PROGRESS now that escrow is created
            order.status = Order.OrderStatus.IN_PROGRESS
            order.save()
            
            logger.info(f"Order {order.order_number} paid and moved to IN_PROGRESS with escrow {escrow_transaction.escrow_id}")
            
            return Response({
                'status': 'Payment processed and escrow created',
                'order_id': order.id,
                'order_number': order.order_number,
                'order_status': order.status,
                'escrow_created': True,
                'escrow_id': escrow_transaction.escrow_id,
                'escrow_status': escrow_transaction.status,
                'total_amount': float(order.total_amount),
                'platform_fee': float(escrow_transaction.platform_fee),
                'freelancer_amount': float(escrow_transaction.freelancer_amount),
                'currency': escrow_transaction.currency,
                'payment_url': escrow_transaction.escrow_response.get('payment_url') if escrow_transaction.escrow_response else None
            })
        else:
            # Escrow creation failed
            logger.error(f"Escrow creation failed for order {order.order_number}")
            return Response(
                {
                    'error': 'Payment received but escrow creation failed. Please contact support.',
                    'order_status': order.status
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def release_payment(self, request, pk=None):
        """
        Client approves work and releases payment from escrow to freelancer.
        """
        order = self.get_object()
        
        # Only client can release payment
        if order.client != request.user:
            return Response(
                {'error': 'Only the client can release payment'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if order.approve_and_release_payment():
            return Response({
                'status': 'Payment released to freelancer',
                'order_status': 'COMPLETED',
                'escrow_status': 'RELEASED'
            })
        
        return Response(
            {'error': 'Cannot release payment for this order'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'])
    def cancel_order(self, request, pk=None):
        """
        Cancel order and refund if applicable.
        """
        order = self.get_object()
        success, message = order.cancel_order(request.user)
        
        if success:
            return Response({'status': message, 'order_status': order.status})
        else:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def submit_deliverable(self, request, pk=None):
        """
        Submit project deliverables with files.
        
        Features:
        - Accepts multiple file uploads
        - Validates deadline and grace period
        - Sanitizes filenames for security
        - Creates Deliverable records for each file
        - Links to order and project
        - Triggers escrow status update
        """
        order = self.get_object()
        
        # Get freelancer from first order item
        first_item = order.items.select_related('freelancer', 'project').first()
        if not first_item:
            return Response(
                {'error': 'Order has no items'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        freelancer = first_item.freelancer
        project = first_item.project
        
        # Only the freelancer can submit deliverables
        if request.user != freelancer:
            return Response(
                {'error': 'Only the assigned freelancer can submit deliverables'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check order status
        if order.status != Order.OrderStatus.IN_PROGRESS:
            return Response(
                {'error': f'Cannot submit deliverables for order in {order.get_status_display()} status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate deadline with 24-hour grace period
        if hasattr(project, 'delivery_days') and project.delivery_days:
            deadline = project.delivery_days
            grace_period = timedelta(hours=24)
            grace_deadline = deadline + grace_period
            
            if timezone.now() > grace_deadline:
                return Response(
                    {'error': 'Submission deadline and grace period have expired. Please contact the client.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Get delivery note
        delivery_note = request.data.get('delivery_note', '').strip()
        if not delivery_note:
            return Response(
                {'error': 'Delivery note is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get uploaded files
        files = []
        for key, value in request.FILES.items():
            if key.startswith('file_'):
                files.append(value)
        
        if not files:
            return Response(
                {'error': 'At least one file must be uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate and sanitize files
        MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
        deliverables_created = []
        
        from Project.models import Deliverable
        
        for file in files:
            # File size validation
            if file.size > MAX_FILE_SIZE:
                return Response(
                    {'error': f'File {file.name} exceeds the 2GB limit'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if file.size == 0:
                return Response(
                    {'error': f'File {file.name} is empty'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Sanitize filename - remove dangerous characters
            safe_filename = re.sub(r'[^a-zA-Z0-9.-_]', '_', file.name)
            
            # Create Deliverable record
            try:
                deliverable = Deliverable.objects.create(
                    project=project,
                    freelancer=freelancer,
                    file=file,
                    description=delivery_note,
                    status=Deliverable.DeliverableStatus.SUBMITTED
                )
                deliverables_created.append({
                    'id': deliverable.id,
                    'filename': safe_filename,
                    'size': file.size,
                    'submitted_at': deliverable.submitted_at.isoformat()
                })
                
                logger.info(f"Deliverable {deliverable.id} created for order {order.order_number} by {freelancer.email}")
                
            except Exception as e:
                logger.error(f"Error creating deliverable: {e}")
                return Response(
                    {'error': f'Failed to upload {safe_filename}: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Update escrow transaction status if exists
        if hasattr(order, 'escrow_transaction'):
            order.escrow_transaction.mark_as_shipped()
            logger.info(f"Escrow transaction {order.escrow_transaction.escrow_id} marked as shipped")
        
        return Response({
            'status': 'Deliverables submitted successfully',
            'order_id': order.id,
            'order_number': order.order_number,
            'deliverables': deliverables_created,
            'total_files': len(deliverables_created),
            'escrow_status': 'SHIPPING' if hasattr(order, 'escrow_transaction') else None,
            'review_period_days': 5,
            'escrow_amount': float(order.total_amount),
            'platform_fee': float(order.total_amount * 0.20),
            'freelancer_amount': float(order.total_amount * 0.80)
        }, status=status.HTTP_201_CREATED)

