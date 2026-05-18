from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Message, Conversation
from .serializers import MessageSerializer, ConversationSerializer


class ConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing conversations.
    Lists all conversations for the authenticated user.
    """
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return conversations where user is a participant"""
        user = self.request.user
        return Conversation.objects.filter(
            Q(participant_1=user) | Q(participant_2=user)
        ).select_related('project', 'participant_1', 'participant_2').prefetch_related('messages')
    
    def create(self, request, *args, **kwargs):
        """
        Create a new conversation or return existing one.
        """
        project_id = request.data.get('project')
        other_user_id = request.data.get('participant_2')
        
        if not project_id or not other_user_id:
            return Response(
                {'error': 'project and participant_2 are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        user = request.user
        
        # Check if conversation already exists (in either direction)
        existing_conversation = Conversation.objects.filter(
            Q(project_id=project_id, participant_1=user, participant_2_id=other_user_id) |
            Q(project_id=project_id, participant_1_id=other_user_id, participant_2=user)
        ).first()
        
        if existing_conversation:
            serializer = self.get_serializer(existing_conversation)
            return Response(serializer.data)
            
        # Create new conversation
        # Ensure consistent ordering if needed, or just create as requested
        # Here we default current user as participant_1
        request.data['participant_1'] = user.id
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark all messages in conversation as read"""
        conversation = self.get_object()
        Message.objects.filter(
            conversation=conversation
        ).exclude(
            sender=request.user
        ).update(is_read=True)
        return Response({'status': 'messages marked as read'})


class MessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing messages within conversations.
    """
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Return messages from conversations where user is a participant"""
        user = self.request.user
        conversation_id = self.request.query_params.get('conversation')
        
        queryset = Message.objects.filter(
            Q(conversation__participant_1=user) | Q(conversation__participant_2=user)
        ).select_related('sender', 'conversation')
        
        if conversation_id:
            queryset = queryset.filter(conversation_id=conversation_id)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set sender to current user when creating message"""
        message = serializer.save(sender=self.request.user)
        
        # Send email notification
        from notifications.email_service import EmailService
        EmailService.send_new_message_email(message)
        
        # Broadcast via WebSocket
        try:
            from notifications.websocket_utils import broadcast_message_received
            
            # Determine recipient (the other participant)
            recipient = message.conversation.get_other_participant(message.sender)
            if recipient:
                broadcast_message_received(recipient.id, message)
        except Exception as e:
            # Don't fail the request if WebSocket fails
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"WebSocket broadcast failed: {e}")
    
    def create(self, request, *args, **kwargs):
        """Override create to mark message as read and update conversation timestamp"""
        response = super().create(request, *args, **kwargs)
        
        # Update conversation's updated_at timestamp
        conversation_id = request.data.get('conversation')
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id)
                conversation.save()  # This triggers auto_now on updated_at
            except Conversation.DoesNotExist:
                pass
        
        return response
