"""
apps/github_sync/oauth.py

GitHub OAuth (Authorization Code) — 학생이 "GitHub 연결" 시 본인 계정 사용 동의를 받는다.
스코프는 public_repo 만 (공개 저장소 쓰기. private/organization 접근 안 함).

GitHub → Settings → Developer settings → OAuth Apps 에서 앱 등록:
    Authorization callback URL = <호스트>/github/callback/
    Client ID / Client Secret 을 .env 에 GITHUB_OAUTH_CLIENT_ID / _CLIENT_SECRET 로.
"""
from __future__ import annotations

from urllib.parse import urlencode

import requests
from django.conf import settings

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
SCOPE = "public_repo"
_TIMEOUT = 15


class OAuthError(Exception):
    pass


def authorize_url(state: str, redirect_uri: str) -> str:
    params = {
        "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    """{access_token, scope, token_type} 반환. 실패 시 OAuthError."""
    try:
        resp = requests.post(
            TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
                "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise OAuthError(f"토큰 교환 요청 실패: {exc}") from exc

    data = resp.json() if resp.content else {}
    if resp.status_code >= 300 or "access_token" not in data:
        raise OAuthError(f"토큰 교환 실패: {data.get('error_description') or resp.text[:200]}")
    return data
