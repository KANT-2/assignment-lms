"""
config/settings/base.py
공통 담당 전담 — 모든 환경(dev/prod)이 공유하는 기본 설정.

환경변수는 .env 에서 로드된다 (manage.py / wsgi.py 에서 load_dotenv 호출).
키 목록과 예시는 .env.example 참고.
"""
import os
from pathlib import Path

# assignment-lms/ (repo 루트)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, str(default)).lower() in ("1", "true", "yes", "on")


def env_list(key: str, default: str = "") -> list[str]:
    raw = env(key, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- 핵심 ---
SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-default-override-in-env")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# --- 애플리케이션 ---
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "widget_tweaks",  # 템플릿에서 폼 위젯 class/속성 조정
]

LOCAL_APPS = [
    "apps.core",             # 공유 모델 (ASSIGNMENT / SUBMISSION / EVALUATION / LECTURE)
    "apps.accounts_client",  # 외부 계정/팀 DB 참조 (managed=False)
    "apps.common",           # base 템플릿 / 공통 static
    "apps.student",          # 학생팀
    "apps.tutor",            # 튜터팀
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # 정적 파일 서빙
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # 각 앱의 templates/ 는 APP_DIRS 로 자동 인식 (apps/common/templates/base.html 포함)
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.common.context_processors.nav",
            ],
        },
    },
]

# --- 데이터베이스 ---
# default  : 이 프로젝트 전용 PostgreSQL (마이그레이션 실제 생성/적용)
# accounts : 외부 계정/팀 DB (읽기 전용, apps.accounts_client 의 managed=False 모델)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "assignment_lms"),
        "USER": env("DB_USER", "postgres"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "5432"),
    },
    "accounts": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("ACCOUNTS_DB_NAME", "accounts"),
        "USER": env("ACCOUNTS_DB_USER", ""),
        "PASSWORD": env("ACCOUNTS_DB_PASSWORD", ""),
        "HOST": env("ACCOUNTS_DB_HOST", "127.0.0.1"),
        "PORT": env("ACCOUNTS_DB_PORT", "5432"),
    },
}

# apps.accounts_client 모델 → accounts DB 로 라우팅. 그 외는 default.
DATABASE_ROUTERS = ["config.routers.AccountsRouter"]

# --- 인증 ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"

# --- 개발 전용: 로그인 우회 ---
# 인증 방식(PRD 9장)이 확정되기 전까지, DEV_SKIP_AUTH=True 이면
#   1) apps.common.middleware.DevAutoLoginMiddleware 가 모든 요청을 고정 dev 유저로 인증 처리
#   2) apps.accounts_client.services 가 외부 accounts DB 대신 가짜 데이터를 반환
# 하여 로그인 화면 없이 화면을 볼 수 있다. prod(config.settings.prod)에서는 절대 켜지 말 것.
DEV_SKIP_AUTH = env_bool("DEV_SKIP_AUTH", False)
DEV_ROLE = (env("DEV_ROLE", "TUTOR") or "TUTOR").upper()  # TUTOR | STUDENT — 볼 화면 선택

# --- 국제화 ---
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# --- 정적 파일 ---
STATIC_URL = "static/"
# 각 앱의 static/ 는 AppDirectoriesFinder 로 자동 인식
STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- 미디어 (과제 제출 첨부파일) ---
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / env("MEDIA_ROOT", "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
