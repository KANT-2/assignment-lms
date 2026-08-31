"""
apps/github_sync/crypto.py

학생 GitHub 액세스 토큰을 DB에 평문으로 두지 않기 위한 대칭 암호화 래퍼.
키는 settings.GITHUB_TOKEN_ENC_KEY (Fernet 키, .env). 미설정 시 이 기능 전체가 비활성이므로
여기서도 키가 없으면 예외를 던진다 (services.enabled() 가 먼저 걸러 준다).

Fernet 키 생성:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

from django.conf import settings
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = getattr(settings, "GITHUB_TOKEN_ENC_KEY", None)
    if not key:
        raise RuntimeError("GITHUB_TOKEN_ENC_KEY 가 설정되지 않았습니다.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(raw: str) -> str:
    return _fernet().encrypt(raw.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
