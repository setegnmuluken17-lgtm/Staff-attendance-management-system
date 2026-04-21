"""
Django settings for SAMS2 project.
"""

import os
from datetime import time
from pathlib import Path

AUTH_USER_MODEL = 'staff.Staff'
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file():
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_int(name, default=0):
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


_load_env_file()

SECRET_KEY = env('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-env')

DEBUG = env_bool('DJANGO_DEBUG', True)

ALLOWED_HOSTS = [host.strip() for host in env('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()]


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'staff',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'SAMS2.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'SAMS2.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': env('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': env('DB_NAME', 'sams_db'),
        'USER': env('DB_USER', 'postgres'),
        'PASSWORD': env('DB_PASSWORD', ''),
        'HOST': env('DB_HOST', 'localhost'),
        'PORT': env('DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTHENTICATION_BACKENDS = [
    'staff.backends.StaffIDBackend',
    'django.contrib.auth.backends.ModelBackend',
]

LANGUAGE_CODE = 'en-us'


TIME_ZONE = 'Africa/Addis_Ababa'
USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
EMAIL_BACKEND = env('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', 'localhost')
EMAIL_PORT = env_int('EMAIL_PORT', 25)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'no-reply@sams.local')

DEFAULT_ADMIN_STAFF_ID = env('DEFAULT_ADMIN_STAFF_ID', 'ADM0001')
DEFAULT_ADMIN_PASSWORD = env('DEFAULT_ADMIN_PASSWORD', '2127')
DEFAULT_ADMIN_FULL_NAME = env('DEFAULT_ADMIN_FULL_NAME', 'System Administrator')
DEFAULT_ADMIN_EMAIL = env('DEFAULT_ADMIN_EMAIL', 'admin@sams.local')
DEFAULT_ADMIN_DEPARTMENT = env('DEFAULT_ADMIN_DEPARTMENT', 'Administration')
DEFAULT_ORGANIZATION_NAME = env('DEFAULT_ORGANIZATION_NAME', 'Bahirdar University')
DEFAULT_ORGANIZATION_CODE = env('DEFAULT_ORGANIZATION_CODE', 'BDU')
DEFAULT_LOCATION_NAME = env('DEFAULT_LOCATION_NAME', 'BIT Location')
DEFAULT_LOCATION_CODE = env('DEFAULT_LOCATION_CODE', 'BIT')

COMPANY_LATITUDE = 9.0300
COMPANY_LONGITUDE = 38.7400
ALLOWED_RADIUS_METERS = 100
OFFICE_IP_PREFIX = "192.168.1."
OFFICE_START_TIME = time(8, 30)
FACE_RECOGNITION_REQUIRED = env_bool('FACE_RECOGNITION_REQUIRED', False)
FACE_IMAGE_MAX_BYTES = env_int('FACE_IMAGE_MAX_BYTES', 3 * 1024 * 1024)

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', not DEBUG)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'
