import os
import secrets
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
env_file = BASE_DIR / '.env'
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

PRODUCTION = os.environ.get('ATLAS_ENV') == 'production'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if PRODUCTION:
        raise RuntimeError('DJANGO_SECRET_KEY must be set in production.')
    secret_path = BASE_DIR / 'data' / '.django-secret'
    secret_path.parent.mkdir(exist_ok=True)
    try:
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as file:
            file.write(secrets.token_urlsafe(64))
    except FileExistsError:
        pass
    SECRET_KEY = secret_path.read_text()

DEBUG = False
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS = list(filter(None, os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')))
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'workspace']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware',
              'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
              'django.contrib.auth.middleware.AuthenticationMiddleware', 'atlas.middleware.ResponsePolicy']
ROOT_URLCONF = 'atlas.urls'
WSGI_APPLICATION = 'atlas.wsgi.application'
AUTH_USER_MODEL = 'workspace.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Casablanca'
USE_TZ = True
APPEND_SLASH = False
CSRF_FAILURE_VIEW = 'workspace.views.csrf_failure'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SECURE = PRODUCTION
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_100_000
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# SQLite is an explicit development/test choice, never a silent PostgreSQL fallback.
if os.environ.get('ATLAS_SQLITE_PATH'):
    if PRODUCTION:
        raise RuntimeError('Production requires PostgreSQL.')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': os.environ['ATLAS_SQLITE_PATH']}}
else:
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError('Configure DATABASE_URL in your private .env file; see .env.example and README.md.')
    url = urlparse(database_url)
    if url.scheme not in ('postgres', 'postgresql'):
        raise RuntimeError('DATABASE_URL must use PostgreSQL.')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': url.path.lstrip('/'),
                           'USER': unquote(url.username or ''), 'PASSWORD': unquote(url.password or ''),
                           'HOST': url.hostname, 'PORT': url.port or 5432, 'CONN_MAX_AGE': 0,
                           'OPTIONS': {'sslmode': os.environ.get('PGSSLMODE', 'prefer')}}}
