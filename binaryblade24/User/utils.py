from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

User = get_user_model()

def get_target_user(request):
    """
    Helper to resolve the target user. 
    If the request user is an admin and a user_id is provided in query params, 
    returns that user. Otherwise returns request.user.
    """
    user_id = request.query_params.get('user_id')
    if user_id and request.user.is_staff:
        return get_object_or_404(User, id=user_id)
    return request.user
