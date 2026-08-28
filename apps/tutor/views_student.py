# apps/tutor/views_student.py
# 👨‍🏫 튜터 — 학생 관리 (모니터링). 목업: docs/mockups/tutor-student-management.html
#
# 목적: 누가 뒤처지는지 / 미제출 관리. 단일 기수 운영이라 라운드 선택 UI 없음.
#
# 스코프 / placeholder (docs/mockups/README.md §5):
#   - 학생 명단 = accounts.get_students() (전체 승인 학생)
#   - 팀: 라운드마다 재편성 + 팀 명단 별도 테이블 미연동 → "미연동" 표시
#   - 제출률: 전체 과제 기준, 개인 과제만 집계 (팀 과제는 학생 귀속 불가 → 분모 제외)
#     · 필수 / 선택 분리
#   - 성적(집계): 방식 미정 → 컬럼 자리만
#   - 체류 시간: 학습 활동 추적 미구현 → 자리만
#   - 마지막 활동: 마지막 제출 시각으로 근사

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts_client import services as accounts
from apps.core.models import Assignment, Submission

SORT_CHOICES = [
    ("required", "필수 제출률 낮은 순"),
    ("name", "이름순"),
    ("last", "마지막 활동 오래된 순"),
]


def tutor_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not accounts.is_tutor(request.user.id):
            raise PermissionDenied("튜터만 접근할 수 있습니다.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def _rate(done, total):
    return round(done / total * 100) if total else None


def _load_students():
    try:
        return list(accounts.get_students() or [])
    except AttributeError:
        return []


# =========================================================
# 학생 목록
# =========================================================

@tutor_required
def student_list(request):
    now = timezone.now()
    students = _load_students()

    assignments = list(Assignment.objects.filter(is_team=False))
    req_ids = {a.id for a in assignments if a.is_required}
    opt_ids = {a.id for a in assignments if not a.is_required}
    # 마감 지난 필수 과제 — "미제출" 판정 대상
    overdue_req_ids = {a.id for a in assignments if a.is_required and a.due_at < now}

    # {student_id: {assignment_id: submission}}
    by_student = {}
    for s in Submission.objects.filter(assignment__is_team=False, student_id__isnull=False):
        by_student.setdefault(s.student_id, {})[s.assignment_id] = s

    rows = []
    students_with_missing = 0
    rate_sum = rate_n = 0
    for stu in students:
        subs = by_student.get(stu.id, {})
        req_done = len(req_ids & subs.keys())
        opt_done = len(opt_ids & subs.keys())
        req_rate = _rate(req_done, len(req_ids))
        missing_required = len(overdue_req_ids - subs.keys())
        if missing_required:
            students_with_missing += 1
        if req_rate is not None:
            rate_sum += req_rate
            rate_n += 1
        last_at = max((s.submitted_at for s in subs.values()), default=None)
        rows.append({
            "id": stu.id,
            "name": stu.name,
            "email": stu.email,
            "req_done": req_done, "req_total": len(req_ids), "req_rate": req_rate,
            "opt_done": opt_done, "opt_total": len(opt_ids), "opt_rate": _rate(opt_done, len(opt_ids)),
            "missing_required": missing_required,
            "last_at": timezone.localtime(last_at) if last_at else None,
        })

    q = (request.GET.get("q") or "").strip()
    if q:
        rows = [r for r in rows if q.lower() in (r["name"] or "").lower()]

    sort = request.GET.get("sort") or "required"
    if sort == "name":
        rows.sort(key=lambda r: r["name"] or "")
    elif sort == "last":
        rows.sort(key=lambda r: (r["last_at"] is not None, r["last_at"] or now))
    else:  # required — 낮은 제출률 먼저 (None 은 뒤로)
        rows.sort(key=lambda r: (r["req_rate"] is None, r["req_rate"] if r["req_rate"] is not None else 0))

    if not students:
        messages.warning(request, "학생 명단을 불러오지 못했습니다 (외부 계정 서비스 미연동).")

    return render(request, "tutor/student_list.html", {
        "rows": rows,
        "total_students": len(students),
        "avg_required_rate": round(rate_sum / rate_n) if rate_n else None,
        "students_with_missing": students_with_missing,
        "filters": {"q": q, "sort": sort},
        "sort_choices": SORT_CHOICES,
    })


# =========================================================
# 학생 상세 — 과제별 제출 이력
# =========================================================

def _submission_status(assignment, submission, now):
    if assignment.is_team:
        return "팀 과제", "team"
    if submission is None:
        return ("미제출", "none") if assignment.due_at < now else ("마감 전", "open")
    if submission.submitted_at > assignment.due_at:
        return "지각 제출", "late"
    return "제출완료", "done"


@tutor_required
def student_detail(request, student_id):
    now = timezone.now()
    student = accounts.get_user(student_id)
    if student is None:
        raise PermissionDenied("학생을 찾을 수 없습니다.")

    subs = {
        s.assignment_id: s
        for s in Submission.objects.filter(student_id=student_id, assignment__is_team=False)
    }

    req_ids = set()
    opt_ids = set()
    timeline = []
    for a in Assignment.objects.all().order_by("-due_at"):
        s = subs.get(a.id)
        if not a.is_team:
            (req_ids if a.is_required else opt_ids).add(a.id)
        label, cls = _submission_status(a, s, now)
        timeline.append({
            "assignment": a,
            "submission": s,
            "status": label, "status_class": cls,
            "submitted_at": timezone.localtime(s.submitted_at) if s else None,
            "score": s.final_score if s else None,
        })

    done = subs.keys()
    last_at = max((s.submitted_at for s in subs.values()), default=None)

    return render(request, "tutor/student_detail.html", {
        "student": student,
        "timeline": timeline,
        "req_rate": _rate(len(req_ids & done), len(req_ids)),
        "opt_rate": _rate(len(opt_ids & done), len(opt_ids)),
        "req_done": len(req_ids & done), "req_total": len(req_ids),
        "opt_done": len(opt_ids & done), "opt_total": len(opt_ids),
        "last_at": timezone.localtime(last_at) if last_at else None,
    })
