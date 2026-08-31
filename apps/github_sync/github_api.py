"""
apps/github_sync/github_api.py

GitHub REST API 얇은 클라이언트 (Contents API 로 파일 커밋). requests 사용.
실패 시 GithubApiError 를 던지고, 호출부(services.sync_one)가 잡아서 재시도 상태로 기록한다.

참고: Contents API 는 파일당 ~50MB 상한. 제출 폼 상한이 30MB(apps/student/forms.py)라 실질적으로 안전.
"""
from __future__ import annotations

import base64
from urllib.parse import quote

import requests

API_ROOT = "https://api.github.com"
_TIMEOUT = 15
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class GithubApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _auth(token: str) -> dict:
    return {**_HEADERS, "Authorization": f"Bearer {token}"}


def _request(method: str, url: str, token: str, **kwargs) -> requests.Response:
    try:
        resp = requests.request(
            method, url, headers=_auth(token), timeout=_TIMEOUT, **kwargs
        )
    except requests.RequestException as exc:  # 네트워크/타임아웃
        raise GithubApiError(f"GitHub 요청 실패: {exc}") from exc
    return resp


def _ok(resp: requests.Response) -> dict:
    if resp.status_code >= 300:
        detail = ""
        try:
            detail = resp.json().get("message", "")
        except ValueError:
            detail = resp.text[:200]
        raise GithubApiError(
            f"GitHub API {resp.status_code}: {detail}", status_code=resp.status_code
        )
    return resp.json() if resp.content else {}


def get_authenticated_user(token: str) -> dict:
    """{id, login, name} — OAuth 로 받은 토큰의 소유자."""
    data = _ok(_request("GET", f"{API_ROOT}/user", token))
    return {"id": data["id"], "login": data["login"], "name": data.get("name") or ""}


def ensure_repo(token: str, login: str, name: str, *, private: bool = False) -> str:
    """저장소가 없으면 생성. full_name (예: 'nelson/lms-assignments') 반환."""
    resp = _request("GET", f"{API_ROOT}/repos/{login}/{name}", token)
    if resp.status_code == 200:
        return resp.json()["full_name"]
    if resp.status_code != 404:
        _ok(resp)  # 404 외 에러는 그대로 올림

    created = _ok(
        _request(
            "POST",
            f"{API_ROOT}/user/repos",
            token,
            json={
                "name": name,
                "private": private,
                "auto_init": False,
                "description": "LMS 과제 제출물 (자동 동기화)",
            },
        )
    )
    return created["full_name"]


def _contents_url(repo: str, path: str) -> str:
    return f"{API_ROOT}/repos/{repo}/contents/{quote(path)}"


def get_file_sha(token: str, repo: str, path: str) -> str | None:
    """경로에 파일이 이미 있으면 그 blob sha, 없으면 None."""
    resp = _request("GET", _contents_url(repo, path), token)
    if resp.status_code == 404:
        return None
    data = _ok(resp)
    if isinstance(data, list):  # 경로가 디렉터리
        raise GithubApiError(f"경로가 디렉터리입니다: {path}")
    return data.get("sha")


def put_file(
    token: str,
    repo: str,
    path: str,
    content: bytes,
    message: str,
    *,
    author_name: str,
    author_email: str,
    sha: str | None = None,
) -> str:
    """파일 생성/갱신. 새 커밋 sha 반환. sha 를 주면 기존 파일 덮어쓰기."""
    payload = {
        "message": message,
        "content": base64.b64encode(content).decode(),
        "author": {"name": author_name, "email": author_email},
        "committer": {"name": author_name, "email": author_email},
    }
    if sha:
        payload["sha"] = sha
    data = _ok(_request("PUT", _contents_url(repo, path), token, json=payload))
    return data["commit"]["sha"]
