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
# ────────────────────────────────────────────────────────────────────────────

from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from apps.accounts_client import services as accounts
from apps.common.preview import _storage_name
from apps.core.models import Assignment, AssignmentFile
from apps.notifications.slack import (
    active_slack_user_ids,
    notify_channel,
    notify_dm_ax_many,
)

from .forms import AssignmentForm

# 과제 첨부 자료(AssignmentFile) 파일 1개당 크기 상한.
MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024  # 50MB


def _save_attachments(assignment, request):
    """과제 등록/수정 POST 에서 첨부 자료를 처리한다.

    - delete_attach: 체크된 기존 AssignmentFile id 삭제 (수정 모드).
    - attach_files: 업로드 파일 (복수). 50MB 초과분은 건너뛰고 이름을 돌려준다.
    - attach_links: 링크 (복수, http/https). 빈 값·중복·형식 오류는 무시.

    반환: 건너뛴 파일명 리스트 (뷰가 messages.warning 으로 안내).
    """

    # 1) 삭제
    del_ids = [
        v for v in request.POST.getlist("delete_attach")
        if v.isdigit()
    ]

    if del_ids:
        doomed = list(
            assignment.attachments.filter(id__in=del_ids)
        )

        for af in doomed:
            if af.kind == AssignmentFile.Kind.FILE and af.file_url:
                try:
                    default_storage.delete(
                        _storage_name(af.file_url)
                    )
                except (OSError, ValueError):
                    pass

        assignment.attachments.filter(
            id__in=del_ids
        ).delete()

    order = (
        assignment.attachments.aggregate(m=Max("order"))["m"] or 0
    ) + 1

    existing_links = set(
        assignment.attachments.filter(
            kind=AssignmentFile.Kind.LINK
        ).values_list("link_url", flat=True)
    )

    skipped = []
    saved_blobs = []

    # 2) 파일 — storage.save() 후 DB row 생성. 중간에 실패하면 저장된 파일을 되돌린다
    #    (안 그러면 디스크에 고아 파일만 남는다).
    try:
        for uploaded in request.FILES.getlist("attach_files"):
            if uploaded.size > MAX_ATTACHMENT_SIZE:
                skipped.append(uploaded.name)
                continue

            safe_name = Path(uploaded.name).name
            storage_name = (
                f"assignment_files/"
                f"{assignment.id}/"
                f"{uuid4().hex}_{safe_name}"
            )

            saved = default_storage.save(
                storage_name,
                uploaded,
            )
            saved_blobs.append(saved)

            AssignmentFile.objects.create(
                assignment=assignment,
                kind=AssignmentFile.Kind.FILE,
                file_url=default_storage.url(saved),
                file_name=safe_name,
                file_size=uploaded.size,
                order=order,
            )

            order += 1
    except Exception:
        for name in saved_blobs:
            try:
                default_storage.delete(name)
            except (OSError, ValueError):
                pass
        raise

    # 3) 링크
    for raw in request.POST.getlist("attach_links"):
        link = raw.strip()

        if not link or link in existing_links:
            continue

        parsed = urlparse(link)

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or len(link) > 200
        ):
            continue

        AssignmentFile.objects.create(
            assignment=assignment,
            kind=AssignmentFile.Kind.LINK,
            link_url=link,
            order=order,
        )

        existing_links.add(link)
        order += 1

    return skipped


# =========================================================
# 공통 — 튜터 권한 체크
# =========================================================

def tutor_required(view_func):
    """로그인 + role=TUTOR 확인."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not accounts.is_tutor(request.user.id):
            raise PermissionDenied(
                "튜터만 접근할 수 있습니다."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped


def _team_deadline():
    """팀 과제 마감일 상한 (없으면 None). AssignmentForm 에 주입한다."""
    period = accounts.get_team_period()
    return period[1] if period else None


def _roster_totals():
    """개인 과제 대상 학생 수 / 팀 과제 대상 팀 수."""

    try:
        student_total = len(
            accounts.get_students() or []
        )
    except AttributeError:
        student_total = 0

    try:
        team_total = len(
            accounts.get_teams() or []
        )
    except AttributeError:
        team_total = 0

    return student_total, team_total


def _assignment_rows():
    """목록 화면용 — 활성 과제 + 제출 건수 + 제출률 분모 + 마감 경과 여부."""

    now = timezone.now()

    student_total, team_total = _roster_totals()

    rows = list(
        Assignment.objects
        .annotate(
            submission_count=Count("submissions")
        )
        .order_by("due_at")
    )

    for a in rows:
        a.unit_total = (
            team_total
            if a.is_team
            else student_total
        )

        a.is_past = a.due_at < now

    return rows


# =========================================================
# FR-001 / FR-002 — 과제 목록 · 등록 · 수정 · 삭제 · 복구
# =========================================================

@tutor_required
def assignment_list(request):
    """GET: 과제 목록, POST: 신규 과제 등록."""

    if request.method == "POST":
        form = AssignmentForm(
            request.POST,
            request.FILES,
            has_submissions=False,
        )

        if form.is_valid():
            assignment = form.save(commit=False)

            assignment.created_by = request.user.id
            assignment.save()

            skipped = _save_attachments(
                assignment,
                request,
            )

            # 과제 등록 완료 후 Slack 채널 알림 (백그라운드)
            notify_channel(
                title="새 과제가 등록되었습니다.",
                message=f"과제명: {assignment.title}",
            )

            messages.success(
                request,
                f"과제 '{assignment.title}'을(를) 등록했습니다.",
            )

            if skipped:
                messages.warning(
                    request,
                    "50MB 초과로 제외된 파일: "
                    + ", ".join(skipped),
                )

            return redirect(
                "tutor:assignment-list"
            )

        messages.error(
            request,
            "입력값을 확인해 주세요.",
        )

    else:
        form = AssignmentForm(team_deadline=_team_deadline())

    return render(
        request,
        "tutor/assignment_manage.html",
        {
            "form": form,
            "form_mode": "create",
            "assignments": _assignment_rows(),
            "deleted_assignments": (
                Assignment.all_objects
                .deleted()
                .order_by("-deleted_at")
            ),
        },
    )


@tutor_required
def assignment_edit(request, pk):
    """GET: 수정 폼, POST: 수정 저장."""

    assignment = get_object_or_404(
        Assignment.objects,
        pk=pk,
    )

    if request.method == "POST":
        form = AssignmentForm(
            request.POST,
            request.FILES,
            instance=assignment,
        )

        if form.is_valid():
            form.save()

            skipped = _save_attachments(
                assignment,
                request,
            )

            messages.success(
                request,
                f"과제 '{assignment.title}'을(를) 수정했습니다.",
            )

            if skipped:
                messages.warning(
                    request,
                    "50MB 초과로 제외된 파일: "
                    + ", ".join(skipped),
                )

            return redirect(
                "tutor:assignment-list"
            )

        messages.error(
            request,
            "입력값을 확인해 주세요.",
        )

    else:
        form = AssignmentForm(
            instance=assignment
        )

    return render(
        request,
        "tutor/assignment_manage.html",
        {
            "form": form,
            "form_mode": "edit",
            "editing": assignment,
            "assignments": _assignment_rows(),
            "deleted_assignments": (
                Assignment.all_objects
                .deleted()
                .order_by("-deleted_at")
            ),
        },
    )


@tutor_required
@require_POST
def assignment_delete(request, pk):
    """소프트 삭제."""

    assignment = get_object_or_404(
        Assignment.objects,
        pk=pk,
    )

    has_submissions = assignment.submissions.exists()

    if (
        has_submissions
        and request.POST.get("confirm") != "yes"
    ):
        messages.warning(
            request,
            f"과제 '{assignment.title}'에는 제출물이 있습니다. "
            "삭제하려면 확인이 필요합니다.",
        )

        return redirect(
            "tutor:assignment-list"
        )

    title = assignment.title

    assignment.delete()

    restore_url = reverse(
        "tutor:assignment-restore",
        args=[assignment.pk],
    )

    messages.success(
        request,
        format_html(
            '과제 \'{}\'을(를) 삭제했습니다. '
            '<form method="post" action="{}" class="d-inline">'
            '<button type="submit" '
            'class="btn btn-link btn-sm p-0 align-baseline">'
            '실행취소'
            '</button>'
            '</form>',
            title,
            restore_url,
        ),
        extra_tags="safe",
    )

    return redirect(
        "tutor:assignment-list"
    )


@tutor_required
@require_POST
def assignment_restore(request, pk):
    """소프트 삭제 취소."""

    assignment = get_object_or_404(
        Assignment.all_objects.deleted(),
        pk=pk,
    )

    assignment.restore()

    messages.success(
        request,
        f"과제 '{assignment.title}' 삭제를 취소했습니다.",
    )

    return redirect(
        "tutor:assignment-list"
    )


# =========================================================
# FR-010 — 제출 현황 대시보드
# =========================================================

SORT_NAME = "name"
SORT_RECENT = "recent"
SORT_UNSUBMITTED_FIRST = "unsubmitted_first"
SORT_PENDING_FIRST = "fb_pending_first"

SORT_DEFAULT = SORT_PENDING_FIRST

SORT_CHOICES = [
    (
        SORT_PENDING_FIRST,
        "피드백 대기 우선",
    ),
    (
        SORT_NAME,
        "이름순",
    ),
    (
        SORT_RECENT,
        "최근 제출순",
    ),
    (
        SORT_UNSUBMITTED_FIRST,
        "미제출 우선",
    ),
]


STATUS_ALL = "all"

STATUS_CHOICES = [
    (
        STATUS_ALL,
        "전체 상태",
    ),
    (
        "submitted",
        "제출 완료",
    ),
    (
        "late",
        "지각 제출",
    ),
    (
        "none",
        "미제출",
    ),
    (
        "fb_pending",
        "피드백 대기",
    ),
    (
        "fb_done",
        "피드백 완료",
    ),
]


class RosterRow:
    """대시보드 한 줄 — 개인 과제는 학생 1명, 팀 과제는 팀 1개."""

    def __init__(
        self,
        unit_id,
        name,
        submission,
        member_names,
        due_at,
    ):
        self.unit_id = unit_id
        self.name = name
        self.submission = submission
        self.member_names = member_names
        self._due_at = due_at

    @property
    def submitted(self):
        return self.submission is not None

    @property
    def submitted_at(self):
        return (
            self.submission.submitted_at
            if self.submission
            else None
        )

    @property
    def is_late(self):
        return bool(
            self.submission
            and self.submission.submitted_at
            > self._due_at
        )

    @property
    def feedback_done(self):
        return bool(
            self.submission
            and self.submission.final_score is not None
        )

    @property
    def feedback_pending(self):
        return bool(
            self.submission
            and self.submission.final_score is None
        )

    @property
    def score(self):
        return (
            self.submission.final_score
            if self.submission
            else None
        )

    @property
    def search_haystack(self):
        return " ".join(
            [
                self.name,
                *self.member_names,
            ]
        ).lower()


@tutor_required
def submission_dashboard(request, pk):
    """과제별 제출/미제출 현황 대시보드."""

    assignment = get_object_or_404(
        Assignment.objects,
        pk=pk,
    )

    submissions = list(
        assignment.submissions.select_related(
            "evaluation",
            "ai_evaluation",
        )
    )

    q = request.GET.get(
        "q",
        "",
    ).strip()

    status = request.GET.get(
        "status",
        STATUS_ALL,
    )

    if status not in dict(STATUS_CHOICES):
        status = STATUS_ALL

    sort = request.GET.get(
        "sort",
        SORT_DEFAULT,
    )

    if sort not in dict(SORT_CHOICES):
        sort = SORT_DEFAULT

    rows = _build_roster(
        assignment,
        submissions,
    )

    total = len(rows)

    submitted_total = sum(
        1
        for r in rows
        if r.submitted
    )

    pending_total = sum(
        1
        for r in rows
        if r.feedback_pending
    )

    feedback_total = sum(
        1
        for r in rows
        if r.feedback_done
    )

    late_total = sum(
        1
        for r in rows
        if r.is_late
    )

    submission_rate = (
        round(
            submitted_total
            / total
            * 100
        )
        if total
        else 0
    )

    # 검색
    if q:
        needle = q.lower()

        rows = [
            r
            for r in rows
            if needle in r.search_haystack
        ]

    # 상태 필터
    _status_pred = {
        "submitted": lambda r: r.submitted,
        "late": lambda r: r.is_late,
        "none": lambda r: not r.submitted,
        "fb_pending": lambda r: r.feedback_pending,
        "fb_done": lambda r: r.feedback_done,
    }.get(status)

    if _status_pred:
        rows = [
            r
            for r in rows
            if _status_pred(r)
        ]

    rows = _sort_rows(
        rows,
        sort,
    )

    return render(
        request,
        "tutor/submission_dashboard.html",
        {
            "assignment": assignment,
            "rows": rows,
            "is_overdue": (
                timezone.now()
                > assignment.due_at
            ),
            "unit_label": (
                "팀"
                if assignment.is_team
                else "명"
            ),
            "stats": {
                "total": total,
                "submitted": submitted_total,
                "unsubmitted": (
                    total
                    - submitted_total
                ),
                "pending": pending_total,
                "feedback": feedback_total,
                "late": late_total,
                "rate": submission_rate,
            },
            "filters": {
                "q": q,
                "status": status,
                "sort": sort,
            },
            "status_choices": STATUS_CHOICES,
            "sort_choices": SORT_CHOICES,
        },
    )


def _build_roster(
    assignment,
    submissions,
):
    """전체 로스터(제출/미제출 모두)를 RosterRow 리스트로."""

    rows = []

    if assignment.is_team:
        sub_by_team = {
            s.team_id: s
            for s in submissions
        }

        for team in (
            accounts.get_teams() or []
        ):
            members = (
                accounts.get_team_members(
                    team.id
                )
                or []
            )

            rows.append(
                RosterRow(
                    unit_id=team.id,
                    name=team.name,
                    submission=sub_by_team.get(
                        team.id
                    ),
                    member_names=[
                        m.name
                        for m in members
                    ],
                    due_at=assignment.due_at,
                )
            )

    else:
        sub_by_student = {
            s.student_id: s
            for s in submissions
        }

        for student in (
            accounts.get_students() or []
        ):
            rows.append(
                RosterRow(
                    unit_id=student.id,
                    name=student.name,
                    submission=sub_by_student.get(
                        student.id
                    ),
                    member_names=[],
                    due_at=assignment.due_at,
                )
            )

    return rows


def _sort_rows(rows, sort):
    if sort == SORT_NAME:
        return sorted(
            rows,
            key=lambda r: r.name,
        )

    if sort == SORT_RECENT:
        submitted = sorted(
            (
                r
                for r in rows
                if r.submitted
            ),
            key=lambda r: r.submitted_at,
            reverse=True,
        )

        unsubmitted = sorted(
            (
                r
                for r in rows
                if not r.submitted
            ),
            key=lambda r: r.name,
        )

        return [
            *submitted,
            *unsubmitted,
        ]

    if sort == SORT_UNSUBMITTED_FIRST:
        return sorted(
            rows,
            key=lambda r: (
                r.submitted,
                r.name,
            ),
        )

    if sort == SORT_PENDING_FIRST:

        def rank(r):
            if r.feedback_pending:
                return 0

            if not r.submitted:
                return 1

            return 2

        return sorted(
            rows,
            key=lambda r: (
                rank(r),
                r.name,
            ),
        )

    return rows


# =========================================================
# 제출 독려 — 미제출 학생/팀에 Slack 개인 DM (백그라운드 발송)
# =========================================================

_REMIND_TITLE = "과제 제출 독려"


def _remind_message(assignment):
    return (
        "아직 제출하지 않은 과제가 있습니다.\n"
        f"과제명: {assignment.title}\n"
        f"마감일: {assignment.due_at:%Y.%m.%d %H:%M}"
    )


def _unsubmitted_recipient_ids(assignment):
    """과제의 미제출 대상 ax_user_id 목록.

    - 개인 과제: 아직 안 낸 학생
    - 팀 과제: 아직 안 낸 팀의 팀원 전원
    """
    if assignment.is_team:
        submitted = set(assignment.submissions.values_list("team_id", flat=True))
        ids = []
        for team in accounts.get_teams() or []:
            if team.id in submitted:
                continue
            ids += [m.id for m in accounts.get_team_members(team.id) or []]
        return ids

    submitted = set(assignment.submissions.values_list("student_id", flat=True))
    return [s.id for s in accounts.get_students() or [] if s.id not in submitted]


def _send_reminders(assignment):
    """assignment 의 미제출 대상에게 독려 DM 을 백그라운드로 발송. (targets, linked) 반환."""
    targets = _unsubmitted_recipient_ids(assignment)
    linked = active_slack_user_ids(targets)
    notify_dm_ax_many(linked, _REMIND_TITLE, _remind_message(assignment))
    return targets, linked


def _remind_result_message(request, total, linked_count):
    if not total:
        messages.info(request, "독려할 미제출 대상이 없습니다.")
    elif linked_count:
        msg = f"미제출 {total}명 중 {linked_count}명에게 제출 독려 DM을 발송했습니다."
        if linked_count < total:
            msg += f" (Slack 미연동 {total - linked_count}명)"
        messages.success(request, msg)
    else:
        messages.warning(
            request, f"미제출 {total}명 모두 Slack 미연동 상태입니다. 연동 상태를 확인해 주세요."
        )


@tutor_required
@require_POST
def submission_remind(request, pk, unit_id):
    """특정 미제출 학생/팀에게 제출 독려 DM (개인=학생 1명, 팀=팀원 전원)."""
    assignment = get_object_or_404(Assignment.objects, pk=pk)

    if assignment.is_team:
        already_submitted = assignment.submissions.filter(team_id=unit_id).exists()
    else:
        already_submitted = assignment.submissions.filter(student_id=unit_id).exists()

    if already_submitted:
        messages.info(request, "이미 제출한 대상입니다.")
        return redirect("tutor:submission-dashboard", pk=assignment.pk)

    if assignment.is_team:
        targets = [m.id for m in accounts.get_team_members(unit_id) or []]
    else:
        targets = [unit_id]

    linked = active_slack_user_ids(targets)
    notify_dm_ax_many(linked, _REMIND_TITLE, _remind_message(assignment))
    _remind_result_message(request, len(targets), len(linked))
    return redirect("tutor:submission-dashboard", pk=assignment.pk)


@tutor_required
@require_POST
def submission_remind_all(request, pk):
    """특정 과제의 모든 미제출 학생/팀원에게 제출 독려 DM."""
    assignment = get_object_or_404(Assignment.objects, pk=pk)
    targets, linked = _send_reminders(assignment)
    _remind_result_message(request, len(targets), len(linked))
    return redirect("tutor:dashboard")


@tutor_required
@require_POST
def submission_remind_all_assignments(request):
    """마감 전 모든 과제의 미제출 학생/팀원에게 제출 독려 DM."""
    now = timezone.now()
    total = linked_total = 0
    for assignment in Assignment.objects.filter(due_at__gte=now):
        targets, linked = _send_reminders(assignment)
        total += len(targets)
        linked_total += len(linked)
    _remind_result_message(request, total, linked_total)
    return redirect("tutor:dashboard")
