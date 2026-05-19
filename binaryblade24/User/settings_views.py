from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .Serializers import (
    UserSerializer, 
    NotificationPreferencesSerializer,
    UserPreferencesSerializer
)
from .models import NotificationPreferences, UserPreferences
from .utils import get_target_user


class ChangePasswordView(APIView):
    """Allow authenticated users to change their password."""
    permission_classes = [IsAuthenticated]

    def put(self, request):
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')

        if not current_password or not new_password:
            return Response(
                {'error': 'Both current_password and new_password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(current_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()
        return Response({'message': 'Password updated successfully'}, status=status.HTTP_200_OK)


class NotificationPreferencesView(APIView):
    """Get or update notification preferences for the authenticated user."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        target_user = get_target_user(request)
        preferences, created = NotificationPreferences.objects.get_or_create(user=target_user)
        serializer = NotificationPreferencesSerializer(preferences)
        return Response(serializer.data)

    def put(self, request):
        target_user = get_target_user(request)
        preferences, created = NotificationPreferences.objects.get_or_create(user=target_user)
        serializer = NotificationPreferencesSerializer(preferences, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserPreferencesView(APIView):
    """Get or update user application preferences for the authenticated user."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        target_user = get_target_user(request)
        preferences, created = UserPreferences.objects.get_or_create(user=target_user)
        serializer = UserPreferencesSerializer(preferences)
        return Response(serializer.data)

    def put(self, request):
        target_user = get_target_user(request)
        preferences, created = UserPreferences.objects.get_or_create(user=target_user)
        serializer = UserPreferencesSerializer(preferences, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserAccountView(APIView):
    """Get or update user account information."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        target_user = get_target_user(request)
        user_data = UserSerializer(target_user, context={'request': request}).data
        # Add profile address if profile exists
        try:
            user_data['address'] = target_user.profile.address or ''
        except:
            user_data['address'] = ''
        return Response(user_data)

    def put(self, request):
        target_user = get_target_user(request)
        # request.data might be an immutable QueryDict if multipart/form-data
        data = request.data.copy() if hasattr(request.data, 'copy') else request.data
        address = data.pop('address', None)
        
        # If it's a list (from QueryDict.pop), get the first item
        if isinstance(address, list) and len(address) > 0:
            address = address[0]

        serializer = UserSerializer(target_user, data=data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            
            # Update profile address if provided
            if address is not None:
                try:
                    profile = target_user.profile
                    profile.address = address
                    profile.save()
                except:
                    pass
            
            # Return updated data including address
            response_data = serializer.data
            try:
                response_data['address'] = target_user.profile.address or ''
            except:
                response_data['address'] = ''
            return Response(response_data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from .countries import COUNTRIES

class CountriesListView(APIView):
    """Return list of all countries for dropdowns."""
    permission_classes = []

    def get(self, request):
        return Response(COUNTRIES)


import pytz

class TimezonesListView(APIView):
    """Return list of all timezones for dropdowns."""
    permission_classes = []

    def get(self, request):
        return Response(pytz.all_timezones)
