"""
config/settings/dev.py
공통 담당 전담 — 로컬 개발 환경.
"""
from .base import *  # noqa: F401,F403
from .base import env_list

DEBUG = True

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# 개발용: 메일은 콘솔로 출력
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --- django-debug-toolbar ---
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    *MIDDLEWARE,  # noqa: F405
]
INTERNAL_IPS = ["127.0.0.1"]
