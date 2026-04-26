"""
Django settings for the Product Customization Engine.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-change-in-production")

DEBUG = os.getenv("DEBUG", "True") == "True"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

# API base URL — passed to the frontend template so JS knows where to call
API_BASE_URL = os.getenv("API_BASE_URL", "/api")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local
    "products",
    "rendering",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serve static files in production
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database — SQLite for development, easily switchable to PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE") or "django.db.backends.sqlite3",
        "NAME": os.getenv("DB_NAME") or str(BASE_DIR / "db.sqlite3"),
        "USER": os.getenv("DB_USER") or "",
        "PASSWORD": os.getenv("DB_PASSWORD") or "",
        "HOST": os.getenv("DB_HOST") or "",
        "PORT": os.getenv("DB_PORT") or "",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS — allow all origins so the JS frontend can call /api/ in both dev and production
CORS_ALLOW_ALL_ORIGINS = True

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    # Use SessionAuthentication so CSRF is enforced via cookie
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "EXCEPTION_HANDLER": "config.exception_handler.custom_exception_handler",
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TIME_LIMIT = 300
# Use 'threads' pool on Windows — prefork (billiard) is broken on Python 3.14
CELERY_WORKER_POOL = "threads"
CELERY_WORKER_CONCURRENCY = os.cpu_count()
# Silence deprecation warning in Celery 5.4+
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# ── Run tasks synchronously in dev so rendering works without a worker ──
# To use the real async worker instead, set env var: CELERY_ASYNC=true
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_ASYNC", "false").lower() != "true"
CELERY_TASK_EAGER_PROPAGATES = True

# Cache — use Redis if available, fall back to in-memory for local dev
_USE_REDIS = os.getenv("USE_REDIS", "false").lower() == "true"
CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://localhost:6379/1"),
            "TIMEOUT": 3600,
        }
        if _USE_REDIS
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "TIMEOUT": 3600,
        }
    )
}

# Rendering Engine Settings
RENDERING = {
    "DISPLACEMENT_SCALE": 14,       # max pixel shift from wrinkle displacement
    "LIGHTING_BLEND_ALPHA": 0.38,   # how strongly fabric shadows show through design
    "PREVIEW_SCALE": 0.5,           # scale for fast synchronous preview
    "CACHE_TTL": 3600,
}

# File upload limits (10 MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ── Logging ──
# Print full tracebacks to stdout/stderr so deployment dashboards show them.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "rendering": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
