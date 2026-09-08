"""
apps/github_sync/views.py — GitHub 연결 / 해제 (학생 · 튜터 공용).

- connect / tutor_connect : state 발급 후 GitHub 동의 화면으로
- callback                : 학생·튜터 공용 1개. 세션 state 로 어느 흐름인지 구분해 처리
                            (OAuth App 에 콜백 URL 을 1개만 등록해도 되게 하려는 것)
- disconnect / tutor_disconnect : 계정 행 삭제 (저장소·커밋·이슈는 그대로 둔다)
"""
from __future__ import annotations

import logging
import secrets
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts_client import services as accounts

from . import github_api, oauth, services
from .models import StudentGithubAccount, TutorGithubAccount

logger = logging.getLogger(__name__)

_STATE_SESSION_KEY = "github_oauth_state"
_TUTOR_STATE_SESSION_KEY = "github_oauth_state_tutor"


def student_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not accounts.is_student(request.user.id):
            raise PermissionDenied("학생만 접근할 수 있습니다.")
        if not services.enabled():
            raise PermissionDenied("GitHub 연동이 비활성화되어 있습니다.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def _external_student_id(request) -> int:
    if getattr(settings, "DEV_SKIP_AUTH", False):
        from apps.student.identity import DEV_STUDENT_ID

        return DEV_STUDENT_ID
    return request.user.id


def _callback_uri(request) -> str:
    return request.build_absolute_uri(reverse("github_sync:callback"))


@student_required
def connect(request):
    state = secrets.token_urlsafe(24)
    request.session[_STATE_SESSION_KEY] = state
    return redirect(oauth.authorize_url(state, _callback_uri(request)))


@login_required
def callback(request):
    """학생·튜터 공용 콜백. 세션에 튜터 state 가 있으면 튜터 흐름, 아니면 학생 흐름."""
    if not services.enabled():
        raise PermissionDenied("GitHub 연동이 비활성화되어 있습니다.")

    state = request.GET.get("state")
    code = request.GET.get("code")
    tutor_state = request.session.pop(_TUTOR_STATE_SESSION_KEY, None)
    student_state = request.session.pop(_STATE_SESSION_KEY, None)

    if tutor_state is not None:
        if state and code and state == tutor_state:
            return _finish_tutor(request, code)
        messages.error(request, "GitHub 연결 요청이 유효하지 않습니다. 다시 시도해 주세요.")
        return redirect("tutor:dashboard")

    if not (state and code and student_state and state == student_state):
        messages.error(request, "GitHub 연결 요청이 유효하지 않습니다. 다시 시도해 주세요.")
        return redirect("student:dashboard")
    return _finish_student(request, code)


def _finish_student(request, code: str):
    if not accounts.is_student(request.user.id):
        raise PermissionDenied("학생만 접근할 수 있습니다.")
    try:
        token_data = oauth.exchange_code(code, _callback_uri(request))
        gh_user = github_api.get_authenticated_user(token_data["access_token"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("github oauth callback 실패: %s", exc)
        messages.error(request, "GitHub 연결에 실패했습니다. 잠시 후 다시 시도해 주세요.")
        return redirect("student:dashboard")

    student_id = _external_student_id(request)
    account, _ = StudentGithubAccount.objects.get_or_create(
        student_id=student_id,
        defaults={"github_user_id": gh_user["id"], "github_login": gh_user["login"]},
    )
    account.github_user_id = gh_user["id"]
    account.github_login = gh_user["login"]
    account.github_name = gh_user["name"]
    account.token_scope = token_data.get("scope", "")
    account.last_error = ""
    account.set_token(token_data["access_token"])
    account.save()

    queued = services.backfill_student(student_id)
    # 소급분 즉시 시도 (보통 몇 건). 실패분은 관리 커맨드가 재시도.
    services.sync_pending(limit=queued or 1)

    messages.success(
        request,
        f"GitHub(@{gh_user['login']}) 연결됨. 제출물 {queued}건을 동기화합니다.",
    )
    return redirect("student:dashboard")


@student_required
@require_POST
def disconnect(request):
    StudentGithubAccount.objects.filter(
        student_id=_external_student_id(request)
    ).delete()
    messages.success(request, "GitHub 연결을 해제했습니다. 이미 올라간 커밋은 그대로 남아 있습니다.")
    return redirect("student:dashboard")


# ─────────────────────────────────────────────────────────────
# 튜터용 — 피드백 이슈 게시에 쓸 GitHub 계정 연결
# ─────────────────────────────────────────────────────────────
def tutor_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not accounts.is_tutor(request.user.id):
            raise PermissionDenied("튜터만 접근할 수 있습니다.")
        if not services.enabled():
            raise PermissionDenied("GitHub 연동이 비활성화되어 있습니다.")
        return view_func(request, *args, **kwargs)

    return _wrapped


@tutor_required
def tutor_connect(request):
    state = secrets.token_urlsafe(24)
    request.session[_TUTOR_STATE_SESSION_KEY] = state
    return redirect(oauth.authorize_url(state, _callback_uri(request)))


def _finish_tutor(request, code: str):
    if not accounts.is_tutor(request.user.id):
        raise PermissionDenied("튜터만 접근할 수 있습니다.")
    try:
        token_data = oauth.exchange_code(code, _callback_uri(request))
        gh_user = github_api.get_authenticated_user(token_data["access_token"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("github oauth tutor callback 실패: %s", exc)
        messages.error(request, "GitHub 연결에 실패했습니다. 잠시 후 다시 시도해 주세요.")
        return redirect("tutor:dashboard")

    account, _ = TutorGithubAccount.objects.get_or_create(
        tutor_id=request.user.id,
        defaults={"github_user_id": gh_user["id"], "github_login": gh_user["login"]},
    )
    account.github_user_id = gh_user["id"]
    account.github_login = gh_user["login"]
    account.github_name = gh_user["name"]
    account.token_scope = token_data.get("scope", "")
    account.last_error = ""
    account.set_token(token_data["access_token"])
    account.save()

    messages.success(
        request,
        f"GitHub(@{gh_user['login']}) 연결됨. 이후 등록하는 피드백이 학생 저장소 이슈로 남습니다.",
    )
    return redirect("tutor:dashboard")


@tutor_required
@require_POST
def tutor_disconnect(request):
    TutorGithubAccount.objects.filter(tutor_id=request.user.id).delete()
    messages.success(request, "GitHub 연결을 해제했습니다. 이미 생성된 이슈는 그대로 남아 있습니다.")
    return redirect("tutor:dashboard")
