"""
Django settings for binaryblade24 project.
"""

from pathlib import Path
import os
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ImproperlyConfigured
import dj_database_url
# Using decouple for environment variable management for consistency and safety
from decouple import config, Csv 
from dotenv import load_dotenv

# Load environment variables from .env file (for local dev environments)
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# ====================================================================
# CORE SECURITY SETTINGS
# ====================================================================

# 🗝️ SECRET_KEY is read from the OS environment variable (set in your WSGI file)
SECRET_KEY = config('SECRET_KEY', default='')

if not SECRET_KEY:
    # Ensures the application fails immediately if the secret key is not set
    raise ImproperlyConfigured("The SECRET_KEY setting must not be empty. Check your WSGI file or environment.")

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG is False by default unless explicitly set to true/1 in the environment.
DEBUG = config('DEBUG', default=False, cast=bool)


# Define the allowed hosts for your application.
# Uses Csv caster to easily load multiple hosts from a single string env variable.
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='binaryblade2411.pythonanywhere.com,morestburawa24.pythonanywhere.com,127.0.0.1,localhost', cast=Csv())


# ====================================================================
# APPLICATION DEFINITION
# ====================================================================

INSTALLED_APPS = [
    'daphne',  # ASGI server - must be first
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Required for sitemaps
    'django.contrib.sitemaps',  # SEO: Sitemap framework
    
    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders', 
    'rest_framework_api_key',
    'channels',  # WebSocket support 
    
    # Your apps
    'User',
    'Project',
    'Proposal',
    'Review',
    'Comment',
    'dashboard',
    'message',
    'notifications',
    'Order',
    'escrow',
]

# SEO: Site ID for sitemap framework
SITE_ID = 1


# Email Configuration (Gmail SMTP)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='morestburawa05@gmail.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = f"BinaryBlade24 <{EMAIL_HOST_USER}>"

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise must be placed immediately after SecurityMiddleware for efficiency
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # CORS middleware must be placed high, before common and CSRF middleware
    'corsheaders.middleware.CorsMiddleware', 
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'binaryblade24.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'binaryblade24.wsgi.application'


# ====================================================================
# DATABASE CONFIGURATION
# ====================================================================

DATABASES = {
    'default': dj_database_url.config(
        # Reads DATABASE_URL from environment or falls back to SQLite
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600
    )
}

# Use the custom user model defined in the User app
AUTH_USER_MODEL = 'User.User'


# ====================================================================
# STATIC & MEDIA FILES AND WHITENOISE
# ====================================================================

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Uses the modern STORAGES setting for WhiteNoise
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# ====================================================================
# AUTHENTICATION & SIMPLE JWT SETTINGS
# ====================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        # You may also want TokenAuthentication or BasicAuthentication here if needed
    )
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}


# ====================================================================
# CORS & CROSS-SITE COOKIE HANDLING
# ====================================================================

# This setting has precedence over CORS_ALLOWED_ORIGINS. Since we want explicit control, 
# we rely on CORS_ALLOWED_ORIGINS and ensure CORS_ALLOW_ALL_ORIGINS is NOT True.
CORS_ALLOW_ALL_ORIGINS = True # Enabled for local development to fix CORS errors

# CORS_ALLOWED_ORIGINS is loaded from environment, defaulting to localhost:3000
# Add your production frontend URLs (e.g., Vercel) to your CORS_ALLOWED_ORIGINS env variable!
# Example of expected env variable: CORS_ALLOWED_ORIGINS=https://my-frontend.com,https://staging.my-frontend.com
# CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')

# Critical for handling cross-site cookies (CSRF token) correctly in the browser
# Set to 'Lax' to ensure cookies are sent with cross-origin POST requests
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True 


# ====================================================================
# PRODUCTION SECURITY & OTHER CONFIGS
# ====================================================================

# These settings are critical for running securely with HTTPS/SSL
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    CSRF_TRUSTED_ORIGINS = ['https://morestburawa24.pythonanywhere.com','https://binaryblade2411.pythonanywhere.com']

# Password validation (unmodified)
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization & Timezones (unmodified)
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Logging Configuration ---
# Standard Python/Django logging setup, using console and file handlers.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'debug.log'),
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'User': { # Logger for your User app
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False, 
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}

# ====================================================================
# ESCROW API CONFIGURATION
# ====================================================================

# Escrow.com API Settings
ESCROW_API_URL = config(
    'ESCROW_API_URL',
    default='https://api.escrow-sandbox.com/2017-09-01'
)
ESCROW_API_EMAIL = config('ESCROW_API_EMAIL', default='')
ESCROW_API_KEY = config('ESCROW_API_KEY', default='')
ESCROW_WEBHOOK_SECRET = config('ESCROW_WEBHOOK_SECRET', default='')

# Platform Fee Configuration (Three-Way Payment Split)
# Platform takes 20%, Freelancer receives 80%
PLATFORM_FEE_PERCENTAGE = Decimal(config('PLATFORM_FEE_PERCENTAGE', default='0.20'))
FREELANCER_PAYOUT_PERCENTAGE = Decimal(config('FREELANCER_PAYOUT_PERCENTAGE', default='0.80'))

# ====================================================================
# WEBSOCKET CONFIGURATION (Django Channels)
# ====================================================================

# ASGI Application
ASGI_APPLICATION = 'binaryblade24.asgi.application'

# Channel Layers - for WebSocket communication
CHANNEL_LAYERS = {
    'default': {
        # Use in-memory for development (no Redis required)
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
        # For production with Redis:
        # 'BACKEND': 'channels_redis.core.RedisChannelLayer',
        # 'CONFIG': {
        #     'hosts': [('127.0.0.1', 6379)],
        # },
    },
}

# ====================================================================
# END OF SETTINGS
# ====================================================================
