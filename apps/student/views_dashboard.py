# apps/student/views_dashboard.py
# 🧑‍🎓 학생 메인 대시보드 (PRD 7장 "학생 대시보드").
# 학생 A(과제 목록/제출)·학생 B(재제출/결과)와 별개 — 이 파일은 홈 대시보드 전용.
#
# 목업: docs/mockups/student-dashboard.html — 아래는 목업에서 바꾼 부분:
#   - 평가 진행률 카드 → "내 과제 현황"으로 대체 (현재 시스템은 과제 제출)
#   - 최근 공개 결과 → 100점 만점 기준 (5점 척도·가중합산은 ERD §4.3 폐기안)
#   - 공지 배너 → 정적 플레이스홀더 (공지 모델 없음)
#   - 캘린더 = Assignment.due_at + Lesson.lesson_date
#
# 외부 계정/팀 데이터는 apps/accounts_client/services.py 헬퍼로만 접근.
# 사용자 role / 네비게이션은 apps/common/context_processors.py 가 처리하므로
# 여기서 nav_role 등을 넘기지 않는다.

import calendar as _calendar
import datetime as dt
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts_client import services as accounts
from apps.core.models import Assignment, Lesson, Submission, Todo

# 공지 모델이 없어 정적 문구로 노출 (목업 배너 자리)
NOTICES = [
    "[안내] 과제 제출 마감은 각 과제의 마감일시 기준입니다.",
    "[안내] 팀 과제는 팀원 누구나 팀을 대신해 제출할 수 있습니다.",
    "[안내] 튜터 평가가 등록되면 해당 제출물은 재제출이 제한됩니다.",
]


@login_required
def home(request):
    """Send users from the site root to the dashboard for their role."""
    if accounts.is_tutor(request.user.id):
        return redirect("tutor:assignment-list")
    if accounts.is_student(request.user.id):
        return redirect("student:dashboard")
    raise PermissionDenied("접근 가능한 역할이 없습니다.")


def student_required(view_func):
    """로그인 + role=STUDENT (accounts.is_student)."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not accounts.is_student(request.user.id):
            raise PermissionDenied("학생만 접근할 수 있습니다.")
        return view_func(request, *args, **kwargs)

    return _wrapped


# =========================================================
# 대시보드
# =========================================================

@student_required
def dashboard(request):
    uid = request.user.id
    today = timezone.localdate()

    year, month = _resolve_month(request, today)
    selected = _resolve_selected_day(request, year, month, today)

    by_day = _calendar_events(year, month)
    weeks = _month_weeks(year, month, today, selected, by_day)

    day_bucket = by_day.get(selected, {})
    day_items = [*day_bucket.get("lecture", []), *day_bucket.get("assignment", [])]

    # 내 팀 (없으면 None)
    team = accounts.get_user_team(uid)
    team_members = accounts.get_team_members(team.id) if team else []

    # 내 제출물 = 내 개인 제출 + (팀이 있으면) 내 팀 제출
    mine = Q(student_id=uid)
    if team:
        mine |= Q(team_id=team.id)

    # 내 과제 현황 (개인 과제 전체 + 팀 과제는 팀이 있을 때)
    my_subs = {s.assignment_id: s for s in Submission.objects.filter(mine)}
    total = submitted = graded = 0
    for a in Assignment.objects.all():
        if a.is_team and not team:
            continue
        total += 1
        s = my_subs.get(a.id)
        if s:
            submitted += 1
            if s.final_score is not None:
                graded += 1
    progress_pct = round(submitted / total * 100) if total else 0

    # 최근 공개 결과 (튜터 평가 완료된 내 제출물 중 최신)
    recent = (
        Submission.objects.filter(mine, final_score__isnull=False)
        .select_related("assignment")
        .order_by("-submitted_at")
        .first()
    )

    todos = Todo.objects.filter(student_id=uid).order_by("is_done", "-created_at")

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)

    return render(
        request,
        "student/dashboard.html",
        {
            "notices": NOTICES,
            "cal": {
                "year": year, "month": month, "weeks": weeks,
                "prev": {"y": prev_y, "m": prev_m},
                "next": {"y": next_y, "m": next_m},
            },
            "selected": selected,
            "day_items": day_items,
            "assign_stats": {
                "total": total, "submitted": submitted, "graded": graded,
                "todo": total - submitted, "pct": progress_pct,
            },
            "recent_result": recent,
            "team": team, "team_members": team_members,
            "todos": todos,
            "todo_done": sum(1 for t in todos if t.is_done),
        },
    )


def _resolve_month(request, today):
    try:
        year = int(request.GET.get("y", today.year))
        month = int(request.GET.get("m", today.month))
        dt.date(year, month, 1)  # 유효성
        return year, month
    except (ValueError, TypeError):
        return today.year, today.month


def _resolve_selected_day(request, year, month, today):
    raw = request.GET.get("d")
    if raw:
        try:
            return dt.date.fromisoformat(raw)
        except ValueError:
            pass
    if (year, month) == (today.year, today.month):
        return today
    return dt.date(year, month, 1)


def _calendar_events(year, month):
    """해당 월의 {date: {"assignment": [...], "lecture": [...]}}."""
    by_day = {}
    for a in Assignment.objects.filter(due_at__year=year, due_at__month=month):
        local = timezone.localtime(a.due_at)
        by_day.setdefault(local.date(), {}).setdefault("assignment", []).append(
            {"kind": "assignment", "title": a.title, "time": local.strftime("%H:%M"), "id": a.id}
        )
    for lesson in Lesson.objects.filter(lesson_date__year=year, lesson_date__month=month):
        by_day.setdefault(lesson.lesson_date, {}).setdefault("lecture", []).append(
            {"kind": "lecture", "title": lesson.title, "time": "", "id": lesson.id}
        )
    return by_day


def _month_weeks(year, month, today, selected, by_day):
    cal = _calendar.Calendar(firstweekday=6)  # 일요일 시작
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        row = []
        for d in week:
            bucket = by_day.get(d, {})
            row.append({
                "date": d,
                "day": d.day,
                "in_month": d.month == month,
                "is_today": d == today,
                "is_selected": d == selected,
                "has_lecture": bool(bucket.get("lecture")),
                "has_assignment": bool(bucket.get("assignment")),
            })
        weeks.append(row)
    return weeks


# =========================================================
# TODO (학생 본인 항목 CRUD — Todo 모델)
# =========================================================

@student_required
@require_POST
def todo_add(request):
    content = (request.POST.get("content") or "").strip()
    if content:
        Todo.objects.create(student_id=request.user.id, content=content[:500])
    return redirect("student:dashboard")


@student_required
@require_POST
def todo_toggle(request, pk):
    todo = get_object_or_404(Todo, pk=pk, student_id=request.user.id)
    todo.is_done = not todo.is_done
    todo.save(update_fields=["is_done"])
    return redirect("student:dashboard")


@student_required
@require_POST
def todo_delete(request, pk):
    Todo.objects.filter(pk=pk, student_id=request.user.id).delete()
    return redirect("student:dashboard")
