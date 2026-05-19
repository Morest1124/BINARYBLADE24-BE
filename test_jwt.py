import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'binaryblade24.settings')
django.setup()

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
import jwt

User = get_user_model()

def test_jwt():
    user = User.objects.first()
    if not user:
        print("No users in DB")
        return
        
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    
    print(f"Token: {access_token}")
    
    try:
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=['HS256'])
        print(f"Decoded with PyJWT (settings.SECRET_KEY): {payload}")
    except Exception as e:
        print(f"Failed to decode with PyJWT (settings.SECRET_KEY): {type(e).__name__} - {e}")
        
        # Try without verify signature
        try:
            payload = jwt.decode(access_token, options={"verify_signature": False})
            print(f"Payload without signature verification: {payload}")
        except Exception as e2:
            print(f"Failed without signature: {e2}")
            
test_jwt()
