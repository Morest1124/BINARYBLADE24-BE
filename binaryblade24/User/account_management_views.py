from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()
from .utils import get_target_user


class DeactivateAccountView(APIView):
    """Deactivate user account (temporary suspension)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.deactivated_at = timezone.now()
        user.is_active = False
        user.save()
        
        return Response({
            'message': 'Account deactivated successfully. You can reactivate it at any time by logging in.',
            'deactivated_at': user.deactivated_at
        }, status=status.HTTP_200_OK)


class ReactivateAccountView(APIView):
    """Reactivate a deactivated account."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.deactivated_at = None
        user.is_active = True
        user.save()
        
        return Response({
            'message': 'Account reactivated successfully.',
        }, status=status.HTTP_200_OK)


class RequestAccountDeletionView(APIView):
    """Request permanent account deletion (30-day grace period)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        deletion_date = timezone.now() + timedelta(days=30)
        user.scheduled_deletion_at = deletion_date
        user.save()
        
        return Response({
            'message': 'Account deletion scheduled. Your account will be permanently deleted in 30 days.',
            'scheduled_deletion_at': deletion_date,
            'days_remaining': 30
        }, status=status.HTTP_200_OK)


class CancelAccountDeletionView(APIView):
    """Cancel a pending account deletion request."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        
        if not user.scheduled_deletion_at:
            return Response({
                'error': 'No pending deletion request found.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user.scheduled_deletion_at = None
        user.save()
        
        return Response({
            'message': 'Account deletion cancelled successfully.',
        }, status=status.HTTP_200_OK)


class AccountStatusView(APIView):
    """Get current account status."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = get_target_user(request)
        
        status_info = {
            'is_active': user.is_active,
            'deactivated_at': user.deactivated_at,
            'scheduled_deletion_at': user.scheduled_deletion_at,
        }
        
        # Calculate days remaining if deletion is scheduled
        if user.scheduled_deletion_at:
            days_remaining = (user.scheduled_deletion_at - timezone.now()).days
            status_info['days_until_deletion'] = max(0, days_remaining)
        
        return Response(status_info, status=status.HTTP_200_OK)
