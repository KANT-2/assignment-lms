# apps/tutor/views_manage.py
# 👨‍🏫 튜터A 전담 — FR-001, FR-002, FR-007, FR-008, FR-010
#
# FR-001 (과제 생성):
#   - 강의 선택 + 과제 정보 입력(제목/설명/마감일/재제출 허용 여부)
#   - 저장: apps.core.models.ASSIGNMENT
#   - 템플릿: tutor/assignment_manage.html
#
# FR-002 (과제 수정/삭제/공개설정):
#   - 기존 과제 편집, 공개/비공개 전환, 삭제(제출물 있으면 경고)
#
# FR-007 (제출 현황 대시보드):
#   - 과제별 제출자/미제출자 목록, 제출률
#   - 템플릿: tutor/submission_dashboard.html
#
# FR-008 (제출물 상세 조회):
#   - 개별 제출물 본문/첨부 확인
#
# FR-010 (재제출 요청):
#   - 특정 제출물에 대해 학생에게 재제출 요청 (상태 변경 + 사유)
#
# 공통: 튜터 권한 체크, 본인 강의 과제만 관리

# ── 구현 메모 ────────────────────────────────────────────────────────────────
# * 위 주석의 FR 번호 매핑은 오래된 초안 잔재다 (PRD v0.3 기준으로는
#   FR-007 지각 허용 / FR-008 필수·선택 라벨 / FR-010 제출 현황 대시보드).
#   이번 작업 범위상 주석은 건드리지 않고 아래 실제 코드만 PRD v0.3 을 따른다.
# * 이번 스코프는 FR-001/002/007/008/010 중 "제출 현황 대시보드"이며,
#   성취율(튜터:AI 가중합산)은 ERD v6 §4.3 에서 폐기된 안이라 포함하지 않는다.
# * 외부 계정/팀 데이터는 apps/accounts_client/services.py 헬퍼로만 접근한다.
#   사용하는 시그니처(문서화된 것):
#       is_tutor(user_id) -> bool
#       get_users(user_ids) -> dict[int, user]
#       get_team_members(team_id) -> list[user]
#   ⚠ 아래 두 함수는 services.py 에 아직 문서화되어 있지 않다. FR-010 의
#     "미제출자 명단"은 전체 로스터가 있어야 성립하므로 공통 담당에게 추가를
#     요청한 상태로 가정하고 호출한다 (미구현이라 지금은 끝까지 실행되지 않음):
#       get_students() -> list[user]         # role=STUDENT, is_active 인 전체 학생
#       get_teams()    -> list[team]         # 이 강의의 전체 팀
# ────────────────────────────────────────────────────────────────────────────

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from apps.accounts_client import services as accounts
from apps.core.models import Assignment

from .forms import AssignmentForm


# =========================================================
# 공통 — 튜터 권한 체크
# =========================================================

def tutor_required(view_func):
    """로그인 + role=TUTOR 확인. request.user.id 를 accounts_user.id 로 간주한다
    (인증 방식은 PRD 9장 열려있는 질문 — 매핑이 확정되면 이 지점만 바꾸면 된다)."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not accounts.is_tutor(request.user.id):
            raise PermissionDenied("튜터만 접근할 수 있습니다.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def _assignment_rows():
    """목록 화면용 — 활성 과제 + 제출 건수."""
    return (
        Assignment.objects.annotate(submission_count=Count("submissions"))
        .order_by("-created_at")
    )


# =========================================================
# FR-001 / FR-002 — 과제 목록 · 등록 · 수정 · 삭제 · 복구
# =========================================================

@tutor_required
def assignment_list(request):
    """GET: 과제 목록,  POST: 신규 과제 등록 (FR-001)."""
    if request.method == "POST":
        form = AssignmentForm(request.POST, has_submissions=False)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.created_by = request.user.id
            assignment.save()
            messages.success(request, f"과제 '{assignment.title}'을(를) 등록했습니다.")
            return redirect("tutor:assignment-list")
        messages.error(request, "입력값을 확인해 주세요.")
    else:
        form = AssignmentForm()

    return render(
        request,
        "tutor/assignment_manage.html",
        {
            "form": form,
            "form_mode": "create",
            "assignments": _assignment_rows(),
            "deleted_assignments": Assignment.all_objects.deleted().order_by("-deleted_at"),
        },
    )


@tutor_required
def assignment_edit(request, pk):
    """GET: 수정 폼,  POST: 수정 저장 (FR-002).
    제출물이 있는 과제는 폼에서 is_team 변경이 막힌다."""
    assignment = get_object_or_404(Assignment.objects, pk=pk)

    if request.method == "POST":
        form = AssignmentForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
            messages.success(request, f"과제 '{assignment.title}'을(를) 수정했습니다.")
            return redirect("tutor:assignment-list")
        messages.error(request, "입력값을 확인해 주세요.")
    else:
        form = AssignmentForm(instance=assignment)

    return render(
        request,
        "tutor/assignment_manage.html",
        {
            "form": form,
            "form_mode": "edit",
            "editing": assignment,
            "assignments": _assignment_rows(),
            "deleted_assignments": Assignment.all_objects.deleted().order_by("-deleted_at"),
        },
    )


@tutor_required
@require_POST
def assignment_delete(request, pk):
    """소프트 삭제 (FR-002). 제출물이 1건이라도 있으면 confirm=yes 가 있어야 진행한다
    (템플릿의 Bootstrap 확인 모달이 이 값을 실어 보낸다)."""
    assignment = get_object_or_404(Assignment.objects, pk=pk)
    has_submissions = assignment.submissions.exists()

    if has_submissions and request.POST.get("confirm") != "yes":
        messages.warning(
            request,
            f"과제 '{assignment.title}'에는 제출물이 있습니다. 삭제하려면 확인이 필요합니다.",
        )
        return redirect("tutor:assignment-list")

    title = assignment.title
    assignment.delete()  # deleted_at 만 채우는 소프트 삭제

    restore_url = reverse("tutor:assignment-restore", args=[assignment.pk])
    messages.success(
        request,
        # messages.html 이 'safe' 태그를 만나면 |safe 로 렌더링한다는 전제
        # (LAYOUT.md §20 공통 템플릿 규약). 아니면 링크가 텍스트로 보일 뿐 기능은 유지.
        format_html(
            '과제 \'{}\'을(를) 삭제했습니다. '
            '<form method="post" action="{}" class="d-inline">'
            '<button type="submit" class="btn btn-link btn-sm p-0 align-baseline">실행취소</button>'
            "</form>",
            title,
            restore_url,
        ),
        extra_tags="safe",
    )
    return redirect("tutor:assignment-list")


@tutor_required
@require_POST
def assignment_restore(request, pk):
    """소프트 삭제 취소 = undo (FR-002)."""
    assignment = get_object_or_404(Assignment.all_objects.deleted(), pk=pk)
    assignment.restore()
    messages.success(request, f"과제 '{assignment.title}' 삭제를 취소했습니다.")
    return redirect("tutor:assignment-list")


# =========================================================
# FR-010 — 제출 현황 대시보드 (성취율 없음, 순수 제출 현황)
# =========================================================

# 정렬 옵션. 앞의 3개는 PRD FR-010 명세.
SORT_NAME = "name"
SORT_RECENT = "recent"
SORT_UNSUBMITTED_FIRST = "unsubmitted_first"
SORT_PENDING_FIRST = "pending_first"  # PRD FR-010 명세 이상의 추가 옵션 (피드백 대기 우선)

SORT_CHOICES = [
    (SORT_NAME, "이름순"),
    (SORT_RECENT, "최근 제출순"),
    (SORT_UNSUBMITTED_FIRST, "미제출 우선"),
    (SORT_PENDING_FIRST, "피드백 대기 우선"),  # PRD FR-010 명세 이상의 추가 옵션
]

STATUS_ALL = "all"
STATUS_SUBMITTED = "submitted"
STATUS_UNSUBMITTED = "unsubmitted"

STATUS_CHOICES = [
    (STATUS_ALL, "전체"),
    (STATUS_SUBMITTED, "제출"),
    (STATUS_UNSUBMITTED, "미제출"),
]


class RosterRow:
    """대시보드 한 줄 — 개인 과제는 학생 1명, 팀 과제는 팀 1개."""

    def __init__(self, unit_id, name, submission, member_names, due_at):
        self.unit_id = unit_id
        self.name = name
        self.submission = submission
        self.member_names = member_names  # 팀 과제일 때만 채워짐 (검색 매칭용/표시용)
        self._due_at = due_at

    @property
    def submitted(self):
        return self.submission is not None

    @property
    def submitted_at(self):
        return self.submission.submitted_at if self.submission else None

    @property
    def is_late(self):
        # BR-004: 튜터 화면에서만 '지각 제출' 구분. Submission 에 별도 컬럼이 없어 파생.
        return bool(self.submission and self.submission.submitted_at > self._due_at)

    @property
    def feedback_done(self):
        return bool(self.submission and self.submission.final_score is not None)

    @property
    def feedback_pending(self):
        return bool(self.submission and self.submission.final_score is None)

    @property
    def search_haystack(self):
        return " ".join([self.name, *self.member_names]).lower()


@tutor_required
def submission_dashboard(request, pk):
    assignment = get_object_or_404(Assignment.objects, pk=pk)
    submissions = list(
        assignment.submissions.select_related("evaluation", "ai_evaluation")
    )

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", STATUS_ALL)
    if status not in dict(STATUS_CHOICES):
        status = STATUS_ALL
    sort = request.GET.get("sort", SORT_NAME)
    if sort not in dict(SORT_CHOICES):
        sort = SORT_NAME

    rows = _build_roster(assignment, submissions)

    total = len(rows)
    submitted_total = sum(1 for r in rows if r.submitted)
    pending_total = sum(1 for r in rows if r.feedback_pending)
    submission_rate = round(submitted_total / total * 100) if total else 0

    # 검색 (팀 과제는 팀원 이름도 매칭)
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in r.search_haystack]

    # 상태 필터
    if status == STATUS_SUBMITTED:
        rows = [r for r in rows if r.submitted]
    elif status == STATUS_UNSUBMITTED:
        rows = [r for r in rows if not r.submitted]

    rows = _sort_rows(rows, sort)

    return render(
        request,
        "tutor/submission_dashboard.html",
        {
            "assignment": assignment,
            "rows": rows,
            "is_overdue": timezone.now() > assignment.due_at,
            "stats": {
                "total": total,
                "submitted": submitted_total,
                "unsubmitted": total - submitted_total,
                "pending": pending_total,
                "rate": submission_rate,
            },
            "filters": {"q": q, "status": status, "sort": sort},
            "status_choices": STATUS_CHOICES,
            "sort_choices": SORT_CHOICES,
        },
    )


def _build_roster(assignment, submissions):
    """전체 로스터(제출/미제출 모두)를 RosterRow 리스트로."""
    rows = []
    if assignment.is_team:
        sub_by_team = {s.team_id: s for s in submissions}
        for team in accounts.get_teams() or []:
            members = accounts.get_team_members(team.id) or []
            rows.append(
                RosterRow(
                    unit_id=team.id,
                    name=team.name,
                    submission=sub_by_team.get(team.id),
                    member_names=[m.name for m in members],
                    due_at=assignment.due_at,
                )
            )
    else:
        sub_by_student = {s.student_id: s for s in submissions}
        for student in accounts.get_students() or []:
            rows.append(
                RosterRow(
                    unit_id=student.id,
                    name=student.name,
                    submission=sub_by_student.get(student.id),
                    member_names=[],
                    due_at=assignment.due_at,
                )
            )
    return rows


def _sort_rows(rows, sort):
    if sort == SORT_NAME:
        return sorted(rows, key=lambda r: r.name)
    if sort == SORT_RECENT:
        # 제출자를 최근 제출 순으로 앞에, 미제출자는 이름순으로 뒤에
        submitted = sorted(
            (r for r in rows if r.submitted),
            key=lambda r: r.submitted_at,
            reverse=True,
        )
        unsubmitted = sorted((r for r in rows if not r.submitted), key=lambda r: r.name)
        return [*submitted, *unsubmitted]
    if sort == SORT_UNSUBMITTED_FIRST:
        return sorted(rows, key=lambda r: (r.submitted, r.name))
    if sort == SORT_PENDING_FIRST:
        # PRD FR-010 명세 이상의 추가 옵션: 피드백 대기(제출O·점수X) → 미제출 → 완료
        def rank(r):
            if r.feedback_pending:
                return 0
            if not r.submitted:
                return 1
            return 2

        return sorted(rows, key=lambda r: (rank(r), r.name))
    return rows
