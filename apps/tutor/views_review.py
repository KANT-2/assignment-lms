"""
apps/tutor/views_review.py — 👨‍🏫 튜터B 전담

FR-011 제출물 검토   : 파일 미리보기 + 학생 설명 + 이전/다음 순차 이동
FR-012 AI 1차 평가   : 튜터가 수동 트리거 → Gemini 점수/코멘트 생성 (재생성 지원, 실패 시 에러 메시지)
FR-013 튜터 평가     : 점수(0~100) + 피드백 저장 → 제출물 잠금(재제출 차단), 이후 수정 가능

진입점: 제출 현황 대시보드(views_manage.submission_dashboard) 의 '제출확인하기' 버튼.
이전/다음 순서는 그 대시보드의 검색/필터/정렬(q, status, sort)을 그대로 이어받는다.

※ tutor_required / 로스터 빌드 로직은 튜터A(views_manage)에 이미 있어 재사용한다.
"""
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.accounts_client import services as accounts
from apps.common.preview import _preview
from apps.core.models import AiEvaluation, Evaluation, Submission

from . import ai_gemini
from .forms import EvaluationForm
from .views_manage import (
    SORT_CHOICES,
    SORT_DEFAULT,
    STATUS_ALL,
    STATUS_CHOICES,
    _build_roster,
    _sort_rows,
    tutor_required,
)

logger = logging.getLogger(__name__)

# 이전/다음 이동 시 유지할 쿼리 파라미터 (대시보드 필터/정렬)
_CARRY_KEYS = ("q", "status", "sort")


def _carry_qs(src) -> str:
    return urlencode({k: src.get(k) for k in _CARRY_KEYS if src.get(k)})


def _review_url(pk, src) -> str:
    url = reverse("tutor:submission-review", args=[pk])
    qs = _carry_qs(src)
    return f"{url}?{qs}" if qs else url


def _review_queue(assignment, q, status, sort):
    """대시보드와 동일한 순서로 정렬된 '제출한' 제출물 리스트 (미제출 제외)."""
    submissions = list(
        assignment.submissions.select_related("evaluation", "ai_evaluation")
    )
    rows = _build_roster(assignment, submissions)

    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in r.search_haystack]

    pred = {
        "submitted": lambda r: r.submitted,
        "late": lambda r: r.is_late,
        "none": lambda r: not r.submitted,
        "fb_pending": lambda r: r.feedback_pending,
        "fb_done": lambda r: r.feedback_done,
    }.get(status)
    if pred:
        rows = [r for r in rows if pred(r)]

    rows = _sort_rows(rows, sort)
    return [r.submission for r in rows if r.submitted]


def _neighbors(assignment, current_pk, params):
    """현재 제출물 기준 이전/다음 pk 와 (현재순번, 전체개수).

    현재 제출물이 status 필터에서 빠졌으면(예: 방금 평가 저장 → fb_pending 에서 제외),
    status 필터를 무시하고 다시 계산해 이동은 계속 되게 한다.
    """
    q = (params.get("q") or "").strip()
    status = params.get("status") if params.get("status") in dict(STATUS_CHOICES) else STATUS_ALL
    sort = params.get("sort") if params.get("sort") in dict(SORT_CHOICES) else SORT_DEFAULT

    pks = [s.pk for s in _review_queue(assignment, q, status, sort)]
    if current_pk not in pks:
        pks = [s.pk for s in _review_queue(assignment, q, STATUS_ALL, sort)]
    if current_pk not in pks:
        return None, None, None

    i = pks.index(current_pk)
    prev_pk = pks[i - 1] if i > 0 else None
    next_pk = pks[i + 1] if i < len(pks) - 1 else None
    return prev_pk, next_pk, (i + 1, len(pks))


def _unit_context(submission):
    """개인=학생 1명 / 팀=팀 1개 (팀원 이름 목록 포함)."""
    if submission.assignment.is_team:
        team = next(
            (t for t in (accounts.get_teams() or []) if t.id == submission.team_id), None
        )
        name = team.name if team else f"팀 #{submission.team_id}"
        members = [m.name for m in (accounts.get_team_members(submission.team_id) or [])]
        return name, members
    student = accounts.get_user(submission.student_id)
    name = student.name if student else f"학생 #{submission.student_id}"
    return name, []


@tutor_required
def submission_review(request, pk):
    submission = get_object_or_404(
        Submission.objects.select_related("assignment"), pk=pk
    )
    assignment = submission.assignment
    evaluation = Evaluation.objects.filter(submission=submission).first()

    if request.method == "POST":
        form = EvaluationForm(request.POST, instance=evaluation)
        if form.is_valid():
            ev = form.save(commit=False)
            ev.submission = submission
            ev.save()  # post_save 시그널 → Submission.final_score / is_locked 동기화
            messages.success(request, "평가를 저장했습니다.")
            return redirect(_review_url(pk, request.POST))
        messages.error(request, "입력값을 확인해주세요.")
    else:
        form = EvaluationForm(instance=evaluation)

    params = request.POST if request.method == "POST" else request.GET
    prev_pk, next_pk, position = _neighbors(assignment, submission.pk, params)
    unit_name, member_names = _unit_context(submission)
    submission.refresh_from_db(fields=["is_locked", "final_score"])

    return render(
        request,
        "tutor/review_panel.html",
        {
            "submission": submission,
            "assignment": assignment,
            "unit_name": unit_name,
            "member_names": member_names,
            "is_late": submission.submitted_at > assignment.due_at,
            "previews": [_preview(f) for f in submission.files.all()],
            "ai": AiEvaluation.objects.filter(submission=submission).first(),
            "evaluation": evaluation,
            "form": form,
            "prev_pk": prev_pk,
            "next_pk": next_pk,
            "position": position,
            "carry_qs": _carry_qs(params),
        },
    )


@tutor_required
@require_POST
def ai_evaluation_generate(request, pk):
    """FR-012 — AI 1차 평가 생성/재생성 (기존 AiEvaluation 을 덮어씀)."""
    submission = get_object_or_404(Submission.objects.select_related("assignment"), pk=pk)
    try:
        result = ai_gemini.generate(submission)
    except Exception:
        logger.exception("AI 1차 평가 생성 실패 (submission=%s)", pk)
        messages.error(request, "AI 1차 평가 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.")
        return redirect(_review_url(pk, request.POST))

    _, created = AiEvaluation.objects.update_or_create(
        submission=submission,
        defaults={"score": result.score, "comment": result.comment},
    )
    messages.success(
        request, "AI 1차 평가를 생성했습니다." if created else "AI 1차 평가를 다시 생성했습니다."
    )
    return redirect(_review_url(pk, request.POST))
