import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import logging

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications and updates.
    Handles escrow updates, order status changes, messages, and notifications.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope['user']
        
        # Reject unauthenticated connections
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt")
            await self.close()
            return
        
        # Create user-specific channel group
        self.group_name = f'user_{self.user.id}'
        
        # Join group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        # Accept the connection
        await self.accept()
        
        logger.info(f"WebSocket connected: user_id={self.user.id}, username={self.user.username}")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'user_id': self.user.id,
            'username': self.user.username,
            'timestamp': self.get_timestamp()
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnect"""
        if hasattr(self, 'group_name'):
            # Leave group
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.info(f"WebSocket disconnected: user_id={self.user.id}, code={close_code}")
    
    async def receive(self, text_data):
        """Receive message from WebSocket client"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # Handle ping/pong for keep-alive
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': self.get_timestamp()
                }))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
    
    # Event handlers (called by channel layer)
    
    async def escrow_update(self, event):
        """Send escrow status update to client"""
        await self.send(text_data=json.dumps({
            'type': 'escrow_update',
            'escrow_id': event['escrow_id'],
            'status': event['status'],
            'order_id': event['order_id'],
            'order_number': event['order_number'],
            'total_amount': event['total_amount'],
            'platform_fee': event['platform_fee'],
            'freelancer_amount': event['freelancer_amount'],
            'timestamp': self.get_timestamp()
        }))
    
    async def order_update(self, event):
        """Send order status update to client"""
        await self.send(text_data=json.dumps({
            'type': 'order_update',
            'order_id': event['order_id'],
            'order_number': event['order_number'],
            'status': event['status'],
            'total_amount': event.get('total_amount'),
            'timestamp': self.get_timestamp()
        }))
    
    async def notification(self, event):
        """Send notification to client"""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification_id': event.get('notification_id'),
            'title': event.get('title'),
            'message': event.get('message'),
            'notification_type': event.get('notification_type'),
            'timestamp': self.get_timestamp()
        }))
    
    async def message_received(self, event):
        """Send new message notification to client"""
        await self.send(text_data=json.dumps({
            'type': 'message_received',
            'message_id': event.get('message_id'),
            'conversation_id': event.get('conversation_id'),
            'sender_id': event.get('sender_id'),
            'sender_name': event.get('sender_name'),
            'body': event.get('body'),
            'timestamp': self.get_timestamp()
        }))
    
    async def deliverable_submitted(self, event):
        """Notify client that freelancer submitted deliverables"""
        await self.send(text_data=json.dumps({
            'type': 'deliverable_submitted',
            'order_id': event['order_id'],
            'order_number': event['order_number'],
            'freelancer_name': event.get('freelancer_name'),
            'file_count': event.get('file_count'),
            'timestamp': self.get_timestamp()
        }))
    
    def get_timestamp(self):
        """Get current ISO timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
