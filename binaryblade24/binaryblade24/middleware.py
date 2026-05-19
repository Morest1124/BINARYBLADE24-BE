from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs
import jwt
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

User = get_user_model()

@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class JwtAuthMiddleware:
    """
    Custom Middleware to authenticate WebSocket connections using JWT.
    
    Expects the token to be passed in the query string:
    ws://domain/path/?token=<jwt_access_token>
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        # Look up user from query string
        query_string = scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token = params.get('token', [None])[0]
        
        scope['user'] = AnonymousUser()
        
        if token:
            try:
                # Decode the token
                # Verify signature using SECRET_KEY
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                user_id = payload.get('user_id')
                
                if user_id:
                    scope['user'] = await get_user(user_id)
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
                # Token invalid or expired
                logger.error(f"JWT Decode Error (Expired/Invalid): {e}")
            except Exception as e:
                # Other errors
                logger.error(f"JWT Decode Error (Other): {type(e).__name__}: {e}")
        
        return await self.app(scope, receive, send)
