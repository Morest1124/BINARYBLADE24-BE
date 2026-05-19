"""
ASGI config for binaryblade24 project.

Exposes the ASGI callable as a module-level variable named ``application``.
"""


import os
from django.conf import settings
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from .middleware import JwtAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'binaryblade24.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import routing after django_asgi_app is created
import notifications.routing

_ws_stack = JwtAuthMiddleware(
    URLRouter(
        notifications.routing.websocket_urlpatterns
    )
)

# In DEBUG mode, skip AllowedHostsOriginValidator so that the Vite
# dev server (localhost:5173) is not rejected due to the Origin header
# containing a port that ALLOWED_HOSTS doesn't explicitly list.
if not settings.DEBUG:
    _ws_stack = AllowedHostsOriginValidator(_ws_stack)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": _ws_stack,
})
