from rest_framework import serializers
from .models import Message, Conversation
from User.models import User, FileAttachment

class UserMinimalSerializer(serializers.ModelSerializer):
    """Minimal user info for message display"""
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'profile_picture']

class FileAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileAttachment
        fields = ['id', 'original_filename', 'file', 'category', 'file_type', 'file_size']

class MessageSerializer(serializers.ModelSerializer):
    sender_details = UserMinimalSerializer(source='sender', read_only=True)
    attachment_details = FileAttachmentSerializer(source='attachment', read_only=True)
    attachment_id = serializers.PrimaryKeyRelatedField(
        queryset=FileAttachment.objects.all(), 
        source='attachment', 
        required=False, 
        allow_null=True,
        write_only=True
    )
    
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'sender_details', 'body', 'timestamp', 'is_read', 'attachment_details', 'attachment_id']
        read_only_fields = ['sender', 'timestamp']


class ConversationSerializer(serializers.ModelSerializer):
    participant_1_details = UserMinimalSerializer(source='participant_1', read_only=True)
    participant_2_details = UserMinimalSerializer(source='participant_2', read_only=True)
    project_title = serializers.CharField(source='project.title', read_only=True)
    project_id = serializers.IntegerField(source='project.id', read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'project', 'project_id', 'project_title',
            'participant_1', 'participant_1_details',
            'participant_2', 'participant_2_details',
            'created_at', 'updated_at',
            'last_message', 'unread_count'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_last_message(self, obj):
        """Get the most recent message in the conversation"""
        last_msg = obj.messages.last()
        if last_msg:
            return {
                'body': last_msg.body,
                'timestamp': last_msg.timestamp,
                'sender': last_msg.sender.username
            }
        return None
    
    def get_unread_count(self, obj):
        """Count unread messages for the current user"""
        request = self.context.get('request')
        if request and request.user:
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0
