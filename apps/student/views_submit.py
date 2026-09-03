"""학생 A — 과제 목록, 개인 과제 제출, 제출 파일 미리보기."""

from datetime import date
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts_client import services as accounts

# 제출 파일 미리보기 로직은 공통(apps/common/preview.py)으로 이동 — 튜터 검토 화면(FR-011)도 사용.
# views_result.py 가 이 모듈에서 import 하므로 여기서 재노출한다.
from apps.common.preview import (  # noqa: F401
    IMAGE_PREVIEW_EXTENSIONS,
    _notebook_cells,
    _preview as _common_preview,
    _read_text,
    _storage_name,
    _submission_kind,
)
from apps.core.models import Assignment, Submission, SubmissionFile
from apps.github_sync import services as github_services

from .forms import AssignmentSubmissionForm, MAX_UPLOAD_SIZE
from .identity import external_student_id

from apps.notifications.slack import send_slack_dm_ax

IMAGE_CONTENT_TYPES = {
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
def _preview(submission_file):
    """이전 import 경로를 유지하면서 공통 미리보기 데이터를 사용한다."""
    preview = _common_preview(submission_file)
    parsed = urlparse(submission_file.file_url)
    preview["is_link"] = (
        submission_file.file_size == 0
        and submission_file.file_name == submission_file.file_url
        and parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
    )
    return preview


def _submitted_resources(request):
    uploaded_files = request.FILES.getlist("files") or request.FILES.getlist("file")
    links = [value.strip() for value in request.POST.getlist("links") if value.strip()]
    if not uploaded_files and not links:
        return uploaded_files, links, "파일 또는 링크를 하나 이상 추가해 주세요."
    for uploaded_file in uploaded_files:
        if uploaded_file.size > MAX_UPLOAD_SIZE:
            return uploaded_files, links, f"{uploaded_file.name}: 파일 크기는 30MB를 초과할 수 없습니다."
    for link in links:
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return uploaded_files, links, "http 또는 https로 시작하는 올바른 링크를 입력해 주세요."
        if len(link) > 200:
            return uploaded_files, links, "링크는 200자 이하로 입력해 주세요."
    return uploaded_files, links, None


def student_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not accounts.is_student(request.user.id):
            raise PermissionDenied("학생만 접근할 수 있습니다.")
        return view_func(request, *args, **kwargs)
    return wrapped




@student_required
def assignment_list(request):
    student_id = request.user.id
    team = accounts.get_user_team(external_student_id(request))
    submission_filter = request.GET.get("submission", "all")
    deadline_filter = request.GET.get("deadline", "all")
    date_group = request.GET.get("date_group", "all")
    created_date_value = request.GET.get("created_date", "")
    if submission_filter not in {"all", "submitted", "unsubmitted"}:
        submission_filter = "all"
    if deadline_filter not in {"all", "open", "closed"}:
        deadline_filter = "all"
    if date_group not in {"all", "month", "day"}:
        date_group = "all"
    try:
        created_date = date.fromisoformat(created_date_value) if created_date_value else None
    except ValueError:
        created_date = None
        created_date_value = ""
    submissions = {
        item.assignment_id: item for item in Submission.objects.filter(
            Q(student_id=student_id, team_id__isnull=True)
            | Q(student_id__isnull=True, team_id=team.id if team else None)
        )
    }
    now = timezone.now()
    rows = []
    for assignment in Assignment.objects.all():
        submission = submissions.get(assignment.id)
        is_past = assignment.due_at < now
        is_late_available = bool(
            is_past and assignment.allow_late and submission is None
        )
        if assignment.is_team and team is None:
            status, status_class = "소속 팀 없음", "secondary"
        elif submission and submission.final_score is not None:
            status, status_class = "평가완료", "primary"
        elif submission and submission.submitted_at > assignment.due_at:
            status, status_class = "지각 제출완료", "warning"
        elif submission:
            status, status_class = "제출완료", "success"
        elif is_late_available:
            status, status_class = "지각 제출 가능", "warning"
        elif is_past:
            status, status_class = "미제출로 마감", "danger"
        else:
            status, status_class = "미제출", "secondary"
        rows.append({
            "assignment": assignment,
            "submission": submission,
            "status": status,
            "status_class": status_class,
            "is_past": is_past,
            "is_late_available": is_late_available,
            "can_submit": (
                submission is None
                and (not assignment.is_team or team is not None)
                and (not is_past or assignment.allow_late)
            ),
            "due_date_str": timezone.localtime(assignment.due_at).strftime('%Y-%m-%d'),
        })
    closed_rows = sorted(
        (row for row in rows if row["is_past"]),
        key=lambda row: (row["assignment"].due_at, row["assignment"].id),
        reverse=True,
    )
    open_rows = sorted(
        (row for row in rows if not row["is_past"]),
        key=lambda row: (row["assignment"].created_at, row["assignment"].id),
        reverse=True,
    )
    rows = closed_rows + open_rows
    filtered_rows = [
        row
        for row in rows
        if (
            submission_filter == "all"
            or (submission_filter == "submitted" and row["submission"] is not None)
            or (submission_filter == "unsubmitted" and row["submission"] is None)
        )
        and (
            deadline_filter == "all"
            or (deadline_filter == "open" and not row["is_past"])
            or (deadline_filter == "closed" and row["is_past"])
        )
        and (
            created_date is None
            or timezone.localtime(row["assignment"].created_at).date() == created_date
        )
    ]
    page_obj = Paginator(filtered_rows, 10).get_page(request.GET.get("page"))
    page_rows = list(page_obj.object_list)
    row_groups = []
    if date_group == "all" and page_rows:
        row_groups.append({"label": "", "rows": page_rows})
    else:
        label_format = "%Y년 %m월" if date_group == "month" else "%Y년 %m월 %d일"
        groups = {}
        for row in page_rows:
            created_at = timezone.localtime(row["assignment"].created_at)
            deadline_label = "마감" if row["is_past"] else "진행 중"
            group_key = (row["is_past"], created_at.strftime(label_format))
            if group_key not in groups:
                group = {
                    "label": f"{deadline_label} · {group_key[1]}",
                    "rows": [],
                }
                groups[group_key] = group
                row_groups.append(group)
            groups[group_key]["rows"].append(row)
    return render(
        request,
        "student/assignment_list.html",
        {
            "rows": page_rows,
            "row_groups": row_groups,
            "total_count": len(rows),
            "filtered_count": len(filtered_rows),
            "page_obj": page_obj,
            "submission_filter": submission_filter,
            "deadline_filter": deadline_filter,
            "date_group": date_group,
            "created_date": created_date_value,
        },
    )


@student_required
def assignment_submit(request, assignment_id):
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    student_id = request.user.id
    team = (
        accounts.get_user_team(external_student_id(request))
        if assignment.is_team
        else None
    )

    if assignment.is_team and team is None:
        messages.error(request, "소속된 팀이 없어 팀 과제를 제출할 수 없습니다.")
        return redirect("student:assignment-list")
    is_late = timezone.now() > assignment.due_at
    if is_late and not assignment.allow_late:
        messages.error(request, "마감되어 더 이상 제출할 수 없는 과제입니다.")
        return redirect("student:assignment-list")

    existing_filter = {
        "assignment": assignment,
        "student_id": None if assignment.is_team else student_id,
        "team_id": team.id if assignment.is_team else None,
    }
    existing = Submission.objects.filter(**existing_filter).first()
    if existing:
        messages.info(
            request,
            "이미 팀원이 제출한 과제입니다. 기존 제출물을 확인해 주세요."
            if assignment.is_team
            else "이미 제출한 과제입니다. 기존 제출물을 확인해 주세요.",
        )
        return redirect("student:assignment-preview", assignment_id=assignment.id)

    form = AssignmentSubmissionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded_files, links, resource_error = _submitted_resources(request)
        if resource_error:
            return render(request, "student/submission_form.html", {
                "assignment": assignment,
                "form": form,
                "resource_error": resource_error,
                "submitted_links": links,
                "is_late": is_late,
            })
        saved_files = []
        submitted_late = False
        try:
            with transaction.atomic():
                locked_assignment = Assignment.objects.select_for_update().get(
                    pk=assignment.id
                )
                submitted_late = timezone.now() > locked_assignment.due_at
                if submitted_late and not locked_assignment.allow_late:
                    messages.error(
                        request,
                        "제출 처리 중 마감 시각이 지나 과제를 제출할 수 없습니다.",
                    )
                    return redirect("student:assignment-list")
                if Submission.objects.filter(**existing_filter).exists():
                    messages.info(
                        request,
                        "다른 팀원이 먼저 제출했습니다. 기존 제출물을 확인해 주세요."
                        if assignment.is_team
                        else "이미 제출한 과제입니다. 기존 제출물을 확인해 주세요.",
                    )
                    return redirect(
                        "student:assignment-preview", assignment_id=assignment.id
                    )
                submission = Submission.objects.create(
                    assignment=locked_assignment,
                    student_id=None if assignment.is_team else student_id,
                    team_id=team.id if assignment.is_team else None,
                    description=form.cleaned_data["description"],
                    last_editor_id=external_student_id(request),
                )
                for uploaded_file in uploaded_files:
                    safe_name = Path(uploaded_file.name).name
                    storage_name = (
                        f"submissions/{student_id}/{uuid4().hex}_{safe_name}"
                    )
                    saved_name = default_storage.save(storage_name, uploaded_file)
                    saved_files.append(saved_name)
                    SubmissionFile.objects.create(
                        submission=submission,
                        kind=_submission_kind(safe_name),
                        file_url=default_storage.url(saved_name),
                        file_name=safe_name,
                        file_size=uploaded_file.size,
                    )
                for link in links:
                    SubmissionFile.objects.create(
                        submission=submission,
                        kind=SubmissionFile.Kind.OTHER,
                        file_url=link,
                        file_name=link,
                        file_size=0,
                    )
        except Exception:
            for saved_name in saved_files:
                default_storage.delete(saved_name)
            raise

        send_slack_dm_ax(
            request.user.id,
            "과제가 제출되었습니다.",
            f"과제명: {assignment.title}",
        )     

        messages.success(request, "과제가 제출되었습니다.")
        return redirect("student:assignment-preview", assignment_id=assignment.id)

    return render(request, "student/submission_form.html", {
        "assignment": assignment,
        "form": form,
        "is_late": is_late,
        "submitted_links": request.POST.getlist("links") if request.method == "POST" else [],
    })


@student_required
def assignment_preview(request, assignment_id):
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    team = (
        accounts.get_user_team(external_student_id(request))
        if assignment.is_team
        else None
    )
    if assignment.is_team and team is None:
        raise PermissionDenied("소속된 팀의 제출물만 볼 수 있습니다.")

    submission = get_object_or_404(
        Submission.objects.select_related(
            "evaluation", "ai_evaluation"
        ).prefetch_related("files"),
        assignment=assignment,
        student_id=None if assignment.is_team else request.user.id,
        team_id=team.id if assignment.is_team else None,
    )
    editor = (
        accounts.get_user(submission.last_editor_id)
        if submission.last_editor_id
        else None
    )
    return render(request, "student/submission_preview.html", {
        "assignment": assignment,
        "submission": submission,
        "last_editor": editor,
        "github_enabled": github_services.enabled(),
        "github_push": getattr(submission, "github_push", None),
        "evaluation": getattr(submission, "evaluation", None),
        "ai_evaluation": getattr(submission, "ai_evaluation", None),
        "is_past": timezone.now() >= assignment.due_at,
        "previews": [_preview(file) for file in submission.files.all()],
        # 팀 과제도 재제출 허용 — 제출물이 팀당 1행이라 팀원 누구나 고치면 전원 반영.
        "can_resubmit": (
            timezone.now() < assignment.due_at
            and not submission.is_locked
        ),
    })


@student_required
def submission_file_download(request, file_id):
    submission_file = get_object_or_404(
        SubmissionFile.objects.select_related("submission__assignment"),
        pk=file_id,
    )
    submission = submission_file.submission
    if submission.team_id is not None:
        team = accounts.get_user_team(external_student_id(request))
        allowed = bool(team and team.id == submission.team_id)
    else:
        allowed = submission.student_id == request.user.id
    if not allowed:
        raise Http404("다운로드할 수 있는 제출 파일이 없습니다.")

    try:
        storage_name = _storage_name(submission_file.file_url)
        file_handle = default_storage.open(storage_name, "rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("저장된 제출 파일을 찾을 수 없습니다.") from None

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=Path(submission_file.file_name).name,
    )


@student_required
def submission_file_image(request, file_id):
    submission_file = get_object_or_404(
        SubmissionFile.objects.select_related("submission__assignment"),
        pk=file_id,
    )
    submission = submission_file.submission
    if submission.team_id is not None:
        team = accounts.get_user_team(external_student_id(request))
        allowed = bool(team and team.id == submission.team_id)
    else:
        allowed = submission.student_id == request.user.id
    extension = Path(submission_file.file_name).suffix.lower()
    if not allowed or extension not in IMAGE_PREVIEW_EXTENSIONS:
        raise Http404("미리 볼 수 있는 이미지가 없습니다.")

    try:
        storage_name = _storage_name(submission_file.file_url)
        file_handle = default_storage.open(storage_name, "rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("저장된 이미지를 찾을 수 없습니다.") from None

    response = FileResponse(
        file_handle,
        as_attachment=False,
        filename=Path(submission_file.file_name).name,
        content_type=IMAGE_CONTENT_TYPES[extension],
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
