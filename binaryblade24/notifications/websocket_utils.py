from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger(__name__)


def broadcast_to_user(user_id, event_type, data):
    """
    Broadcast event to specific user via WebSocket.
    
    Args:
        user_id: The ID of the user to send the message to
        event_type: Type of event (e.g., 'escrow_update', 'order_update')
        data: Dictionary containing event data
    """
    try:
        channel_layer = get_channel_layer()
        group_name = f'user_{user_id}'
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': event_type,
                **data
            }
        )
        logger.info(f"Broadcast {event_type} to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast {event_type} to user {user_id}: {e}")


def broadcast_escrow_update(user_id, escrow_transaction):
    """Broadcast escrow status update to user"""
    broadcast_to_user(user_id, 'escrow_update', {
        'escrow_id': escrow_transaction.escrow_id,
        'status': escrow_transaction.status,
        'order_id': escrow_transaction.order.id,
        'order_number': escrow_transaction.order.order_number,
        'total_amount': float(escrow_transaction.total_amount),
        'platform_fee': float(escrow_transaction.platform_fee),
        'freelancer_amount': float(escrow_transaction.freelancer_amount)
    })


def broadcast_order_update(user_id, order):
    """Broadcast order status update to user"""
    broadcast_to_user(user_id, 'order_update', {
        'order_id': order.id,
        'order_number': order.order_number,
        'status': order.status,
        'total_amount': float(order.total_amount)
    })


def broadcast_notification(user_id, notification):
    """Broadcast notification to user"""
    broadcast_to_user(user_id, 'notification', {
        'notification_id': notification.id if hasattr(notification, 'id') else None,
        'title': getattr(notification, 'title', 'Notification'),
        'message': getattr(notification, 'message', ''),
       'notification_type': getattr(notification, 'notification_type', 'info')
    })


def broadcast_deliverable_submitted(user_id, order, file_count):
    """Broadcast deliverable submission notification"""
    freelancer_name = order.items.first().freelancer.username if order.items.exists() else 'Freelancer'
    
    broadcast_to_user(user_id, 'deliverable_submitted', {
        'order_id': order.id,
        'order_number': order.order_number,
        'freelancer_name': freelancer_name,
        'file_count': file_count
    })

def broadcast_message_received(user_id, message):
    """Broadcast new message to user"""
    broadcast_to_user(user_id, 'message_received', {
        'message_id': message.id,
        'conversation_id': message.conversation.id,
        'sender_id': message.sender.id,
        'sender_name': message.sender.username,
        'body': message.body
    })

def broadcast_proposal_received(user_id, proposal):
    """Broadcast new proposal to client"""
    broadcast_to_user(user_id, 'proposal_received', {
        'proposal_id': proposal.id,
        'project_id': proposal.project.id,
        'project_title': proposal.project.title,
        'freelancer_id': proposal.freelancer.id,
        'freelancer_name': proposal.freelancer.username,
        'bid_amount': float(proposal.bid_amount)
    })

def broadcast_proposal_status_update(user_id, proposal):
    """Broadcast proposal status update to freelancer"""
    broadcast_to_user(user_id, 'proposal_status_update', {
        'proposal_id': proposal.id,
        'project_id': proposal.project.id,
        'project_title': proposal.project.title,
        'status': proposal.status
    })
