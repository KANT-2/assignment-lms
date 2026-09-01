"""
apps/tutor/github_fetch.py — 👨‍🏫 튜터B

학생이 과제 제출 시 넣은 GitHub **공개 레포 단일 파일(blob)** 링크를 받아온다.
AI 채점(ai_gemini)이 그 코드를 프롬프트에 넣어 참고한다.

- 무인증 (공개 레포만). GITHUB_API_TOKEN 있으면 헤더에 실어 rate limit 여유.
- github.com / raw.githubusercontent.com 만 허용 (SSRF 방어).
- blob·raw 단일 파일만. 레포 루트·tree·PR·gist 는 미지원 (None 반환).
- 실패는 예외 대신 None. 설계: docs/assignment-lms-github-link-eval.md
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from django.conf import settings

_ALLOWED_HOSTS = {"github.com", "www.github.com", "raw.githubusercontent.com"}
_TIMEOUT = 10
_MAX_BYTES = 512 * 1024  # 이보다 큰 파일은 스킵 (데이터/바이너리로 간주)

# /{owner}/{repo}/blob/{ref}/{path...}
_BLOB_RE = re.compile(r"^/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")


def is_github_url(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "").lower() in _ALLOWED_HOSTS
    except ValueError:
        return False


def raw_url(url: str) -> str | None:
    """단일 파일 raw URL 로 변환. blob·raw 가 아니면 None."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host == "raw.githubusercontent.com":
        return f"https://raw.githubusercontent.com{parsed.path}"
    match = _BLOB_RE.match(parsed.path)
    if not match:
        return None
    owner, repo, ref, path = match.groups()
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"


def fetch_github_file(url: str) -> str | None:
    """공개 레포 단일 파일의 텍스트 내용. 실패(비-github·비-blob·404·비공개·타임아웃·바이너리) 시 None."""
    if not is_github_url(url):
        return None
    target = raw_url(url)
    if target is None:
        return None

    headers = {}
    token = getattr(settings, "GITHUB_API_TOKEN", "") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(target, timeout=_TIMEOUT, headers=headers)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or len(resp.content) > _MAX_BYTES:
        return None
    try:
        return resp.content.decode("utf-8")
    except UnicodeDecodeError:
        return None
