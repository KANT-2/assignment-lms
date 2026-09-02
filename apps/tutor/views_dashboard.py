# apps/tutor/views_dashboard.py
# 👨‍🏫 튜터 메인 대시보드 — 로그인 후 첫 화면.
# 목업: docs/mockups/tutor-dashboard.html
#
# 구성:
#   - 한 줄 요약 (진행 중 과제 / 피드백 대기 / 마감 임박 / 오늘 신규 제출 / 강의안 차시)
#   - 진행 중인 과제: 제출·피드백 진행률 + 상태 → 클릭 시 제출 현황
#   - 피드백 대기 목록: 마감 지난 미평가 제출물 → 클릭 시 검토 화면
#   - 미제출 학생 현황: 마감 전 과제별 미제출 인원 → 클릭 시 제출 현황
#     · Slack 독려는 UI만 (연동 인프라 없음 → 버튼 비활성)
#   - 강의안 준비 현황: 차시별 영상·교안 등록 상태 (교안은 선택)
#
# 외부 계정/팀 데이터는 apps/accounts_client/services.py 헬퍼로만 접근.
# 제출률 분모(전체 학생 수 / 팀 수)는 services 미구현 단계에서 0 으로 폴백한다.

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from apps.accounts_client import services as accounts
from apps.core.models import Assignment, Lesson, Submission

FEEDBACK_QUEUE_LIMIT = 12
LESSON_LIMIT = 12
URGENT_DAYS = 1
IMMINENT_DAYS = 3
ONGOING_LIMIT = 8

# 대시보드 상단 인사말 — 접속 시각(Asia/Seoul)의 '시'로 구간을 나눈다.
# (시작 시각 오름차순. 마지막 구간이 자정을 넘어 다음날 새벽까지 이어진다.)
_GREETINGS = [
    (5, "☀️ 좋은 아침입니다. 오늘도 힘차게 시작해요"),
    (11, "🍚 점심 든든히 드셨나요? 오후도 화이팅이에요"),
    (14, "☕ 나른한 오후네요. 커피 한 잔 어떠세요"),
    (17, "🌆 곧 퇴근이에요! 오늘 마무리 화이팅"),
    (19, "🌙 오늘도 수고 많으셨어요"),
    (23, "🌛 늦게까지 고생이 많으세요. 무리하지 마세요"),
]


def _greeting(now_local) -> str:
    """접속 시각에 맞는 인사말. now_local 은 이미 로컬타임인 datetime."""
    hour = now_local.hour
    text = _GREETINGS[-1][1]  # 23시~04시 (자정 넘김)
    for start, message in _GREETINGS:
        if hour >= start:
            text = message
    return text


def tutor_required(view_func):
    """로그인 + role=TUTOR (accounts.is_tutor)."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not accounts.is_tutor(request.user.id):
            raise PermissionDenied("튜터만 접근할 수 있습니다.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def _roster_totals():
    """개인 과제 분모(전체 학생 수) / 팀 과제 분모(팀 수). services 미구현 시 0."""
    try:
        student_total = len(accounts.get_students() or [])
    except AttributeError:
        student_total = 0
    try:
        team_total = len(accounts.get_teams() or [])
    except AttributeError:
        team_total = 0
    return student_total, team_total


def _pct(part, whole):
    return round(part / whole * 100) if whole else 0


def _ongoing_status(is_past, dday, sub_count, fb_count):
    if is_past and sub_count and fb_count >= sub_count:
        return "피드백 완료", "done"
    if is_past:
        return "마감 · 검토 중", "closed"
    if 0 <= dday <= URGENT_DAYS:
        return "마감 임박", "imminent"
    if dday <= IMMINENT_DAYS:
        return "마감 임박", "soon"
    return "진행 중", "open"


@tutor_required
def dashboard(request):
    now = timezone.now()
    today = timezone.localdate()
    greeting = _greeting(timezone.localtime(now))
    student_total, team_total = _roster_totals()

    active = list(
        Assignment.objects.annotate(
            sub_count=Count("submissions", distinct=True),
            fb_count=Count(
                "submissions",
                filter=Q(submissions__evaluation__isnull=False),
                distinct=True,
            ),
        ).order_by("due_at")
    )

    # ── 진행 중인 과제 ──
    rows, imminent_count, ongoing_count = [], 0, 0
    for a in active:
        unit_total = team_total if a.is_team else student_total
        dday = (timezone.localtime(a.due_at).date() - today).days
        is_past = a.due_at < now
        status, status_class = _ongoing_status(is_past, dday, a.sub_count, a.fb_count)
        if not is_past:
            ongoing_count += 1
            if 0 <= dday <= IMMINENT_DAYS:
                imminent_count += 1
        rows.append({
            "obj": a,
            "unit_total": unit_total,
            "unit_label": "팀" if a.is_team else "명",
            "dday": dday,
            "is_past": is_past,
            "sub_count": a.sub_count,
            "fb_count": a.fb_count,
            "sub_pct": _pct(a.sub_count, unit_total),
            "fb_pct": _pct(a.fb_count, a.sub_count),
            "status": status,
            "status_class": status_class,
        })
    # 마감 전(임박순) → 최근 마감 순으로, 상위 N개만
    upcoming = [r for r in rows if not r["is_past"]]
    closed = sorted((r for r in rows if r["is_past"]), key=lambda r: r["obj"].due_at, reverse=True)
    ongoing_rows = (upcoming + closed)[:ONGOING_LIMIT]

    # ── 피드백 대기 (마감 지남 + 튜터 평가 없음) ──
    pending_qs = Submission.objects.filter(
        assignment__due_at__lt=now, evaluation__isnull=True
    ).select_related("assignment")
    pending_count = pending_qs.count()
    pending_subs = list(pending_qs.order_by("-submitted_at")[:FEEDBACK_QUEUE_LIMIT])

    user_ids = [s.student_id for s in pending_subs if s.student_id]
    users = accounts.get_users(user_ids) if user_ids else {}
    teams_by_id = {}
    if any(s.team_id for s in pending_subs):
        teams_by_id = {t.id: t for t in (accounts.get_teams() or [])}

    feedback_queue = []
    for s in pending_subs:
        if s.team_id:
            team = teams_by_id.get(s.team_id)
            who = team.name if team else f"{s.team_id}팀"
            is_team = True
        else:
            user = users.get(s.student_id)
            who = user.name if user else f"학생 #{s.student_id}"
            is_team = False
        feedback_queue.append({
            "submission_id": s.id,
            "who": who,
            "is_team": is_team,
            "assignment_title": s.assignment.title,
            "submitted_at": timezone.localtime(s.submitted_at),
            "is_locked": s.is_locked,
        })

    # ── 미제출 학생 현황 (마감 전 과제, 미제출 > 0) ──
    not_submitted = []
    for r in rows:
        if r["is_past"]:
            continue
        missing = r["unit_total"] - r["sub_count"]
        if missing <= 0:
            continue
        not_submitted.append({
            "assignment_id": r["obj"].id,
            "title": r["obj"].title,
            "due": timezone.localtime(r["obj"].due_at),
            "dday": r["dday"],
            "is_team": r["obj"].is_team,
            "missing": missing,
            "unit_label": r["unit_label"],
        })

    # ── 강의안 준비 현황 ──
    lesson_rows = []
    prep_needed = 0
    for lesson in (
        Lesson.objects.annotate(
            mat_count=Count("materials"),
            video_count=Count("videos")
        ).order_by("-lesson_date")[:LESSON_LIMIT]
    ):
        has_video = lesson.video_count > 0
        is_past = lesson.lesson_date < today
        needs_attention = is_past and not has_video and lesson.mat_count == 0
        if needs_attention:
            prep_needed += 1
        lesson_rows.append({
            "id": lesson.id,
            "title": lesson.title,
            "date": lesson.lesson_date,
            "has_video": has_video,
            "mat_count": lesson.mat_count,
            "is_past": is_past,
            "needs_attention": needs_attention,
        })

    summary = {
        "ongoing": ongoing_count,
        "pending": pending_count,
        "imminent": imminent_count,
        "new_today": Submission.objects.filter(submitted_at__date=today).count(),
        "lessons": Lesson.objects.count(),
    }

    return render(
        request,
        "tutor/dashboard.html",
        {
            "greeting": greeting,
            "summary": summary,
            "ongoing_rows": ongoing_rows,
            "feedback_queue": feedback_queue,
            "feedback_pending_count": pending_count,
            "not_submitted": not_submitted,
            "lesson_rows": lesson_rows,
            "lesson_total": summary["lessons"],
            "lesson_prep_needed": prep_needed,
            "slack_connected": False,  # 연동 인프라 미구현
        },
    )
