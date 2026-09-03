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
    "apps.github_sync",      # 제출물 → 학생 개인 GitHub 저장소 자동 push
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
    # AX2 통합 플랫폼 (ax_evaluation) — VIEW 읽기 전용. 마이그레이션·write 안 함.
    "accounts": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("ACCOUNTS_DB_NAME", "ax_evaluation"),
        "USER": env("ACCOUNTS_DB_USER", ""),
        "PASSWORD": env("ACCOUNTS_DB_PASSWORD", ""),
        "HOST": env("ACCOUNTS_DB_HOST", "127.0.0.1"),
        "PORT": env("ACCOUNTS_DB_PORT", "5432"),
        "OPTIONS": {"options": "-c default_transaction_read_only=on"},
    },
}

# apps.accounts_client 모델 → accounts DB 로 라우팅. 그 외는 default.
DATABASE_ROUTERS = ["config.routers.AccountsRouter"]

# 우리 강의에 해당하는 AX2 평가 라운드. 비우면 IN_PROGRESS 라운드를 자동 선택
# (apps.accounts_client.services._current_round_id). 특정 라운드 고정 시 숫자 지정.
AX_ROUND_ID = env("AX_ROUND_ID", None)

# --- AI 1차 평가 (FR-012) ---
# apps.tutor.ai_gemini 가 이 키로 Gemini 를 호출한다.
# 키 미설정 / 호출 실패 시엔 뷰가 "AI 평가 생성에 실패했습니다" 메시지를 띄운다 (가짜 점수 저장 안 함).
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.6-flash")
# 1순위 모델이 5xx(혼잡)일 때 순서대로 재시도할 폴백 모델. 무료 티어는 모델별로
# 혼잡이 오락가락해서 하나 걸어두면 성공률이 올라간다. 비우면 재시도 없음.
GEMINI_FALLBACK_MODELS = env_list("GEMINI_FALLBACK_MODELS", "gemini-flash-latest")

# --- GitHub 제출물 동기화 (apps.github_sync) ---
# 세 값이 모두 있어야 기능 활성화 (services.enabled()). 없으면 시그널·UI 모두 no-op.
# OAuth App: GitHub → Settings → Developer settings → OAuth Apps
#   Authorization callback URL = <호스트>/github/callback/
# 토큰 암호화 키: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
GITHUB_OAUTH_CLIENT_ID = env("GITHUB_OAUTH_CLIENT_ID")
GITHUB_OAUTH_CLIENT_SECRET = env("GITHUB_OAUTH_CLIENT_SECRET")
GITHUB_TOKEN_ENC_KEY = env("GITHUB_TOKEN_ENC_KEY")
GITHUB_SUBMISSION_REPO_NAME = env("GITHUB_SUBMISSION_REPO_NAME", "lms-assignments")

# AI 채점이 학생 GitHub 공개 레포 단일 파일 링크를 읽을 때 rate limit 상향용 (apps.tutor.github_fetch).
# 없어도 동작 (무인증, 60/hr). 있으면 5000/hr.
GITHUB_API_TOKEN = env("GITHUB_API_TOKEN")

# --- 인증 ---
# 실제 로그인: ax_evaluation.accounts_user 이메일+비번 (AxPasswordBackend).
# ModelBackend 는 dev 유저(DevAutoLoginMiddleware가 만든 로컬 계정)용으로 남겨둔다.
AUTHENTICATION_BACKENDS = [
    "apps.accounts_client.backends.AxPasswordBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"

# --- 개발 전용: 로그인 우회 (오프라인 / 자동테스트 폴백) ---
# 평소엔 False (실제 로그인). DEV_SKIP_AUTH=True 이면
#   1) apps.common.middleware.DevAutoLoginMiddleware 가 요청을 고정 dev 유저로 인증
#   2) apps.accounts_client.services 가 ax_evaluation DB 대신 가짜 데이터를 반환
# 하여 네트워크/DB 없이 화면·테스트가 가능하다. prod 에서는 절대 켜지 말 것.
DEV_SKIP_AUTH = env_bool("DEV_SKIP_AUTH", False)
DEV_ROLE = (env("DEV_ROLE", "TUTOR") or "TUTOR").upper()  # TUTOR | STUDENT — 볼 화면 선택
DEV_USER_ID = 999999  # dev 유저 로컬 id (실제 accounts_user id 와 안 겹치게)

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
