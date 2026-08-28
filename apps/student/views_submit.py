"""학생 A — 과제 목록, 개인 과제 제출, 제출 파일 미리보기."""

from functools import wraps
from pathlib import Path
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts_client import services as accounts

# 제출 파일 미리보기 로직은 공통(apps/common/preview.py)으로 이동 — 튜터 검토 화면(FR-011)도 사용.
# views_result.py 가 이 모듈에서 import 하므로 여기서 재노출한다.
from apps.common.preview import (  # noqa: F401
    _notebook_cells,
    _preview,
    _read_text,
    _storage_name,
    _submission_kind,
)
from apps.core.models import Assignment, Submission, SubmissionFile

from .forms import SubmissionForm
from .identity import external_student_id


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
    if submission_filter not in {"all", "submitted", "unsubmitted"}:
        submission_filter = "all"
    if deadline_filter not in {"all", "open", "closed"}:
        deadline_filter = "all"
    submissions = {
        item.assignment_id: item for item in Submission.objects.filter(
            Q(student_id=student_id, team_id__isnull=True)
            | Q(student_id__isnull=True, team_id=team.id if team else None)
        )
    }
    now = timezone.now()
    rows = []
    for assignment in Assignment.objects.all().order_by("due_at"):
        submission = submissions.get(assignment.id)
        if assignment.is_team and team is None:
            status, status_class = "소속 팀 없음", "secondary"
        elif submission and submission.final_score is not None:
            status, status_class = "평가완료", "primary"
        elif submission:
            status, status_class = "제출완료", "success"
        elif assignment.due_at < now:
            status, status_class = "미제출로 마감", "danger"
        else:
            status, status_class = "미제출", "secondary"
        rows.append({
            "assignment": assignment,
            "submission": submission,
            "status": status,
            "status_class": status_class,
            "is_past": assignment.due_at < now,
            "can_submit": (
                submission is None
                and (not assignment.is_team or team is not None)
                and assignment.due_at >= now
            ),
            "due_date_str": timezone.localtime(assignment.due_at).strftime('%Y-%m-%d'),
        })
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
    ]
    return render(
        request,
        "student/assignment_list.html",
        {
            "rows": filtered_rows,
            "total_count": len(rows),
            "submission_filter": submission_filter,
            "deadline_filter": deadline_filter,
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
    if timezone.now() > assignment.due_at:
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

    form = SubmissionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded_file = form.cleaned_data["file"]
        safe_name = Path(uploaded_file.name).name
        storage_name = f"submissions/{student_id}/{uuid4().hex}_{safe_name}"
        saved_name = None
        try:
            with transaction.atomic():
                locked_assignment = Assignment.objects.select_for_update().get(
                    pk=assignment.id
                )
                if timezone.now() > locked_assignment.due_at:
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
                saved_name = default_storage.save(storage_name, uploaded_file)
                submission = Submission.objects.create(
                    assignment=locked_assignment,
                    student_id=None if assignment.is_team else student_id,
                    team_id=team.id if assignment.is_team else None,
                    description=form.cleaned_data["description"],
                    last_editor_id=external_student_id(request),
                )
                SubmissionFile.objects.create(
                    submission=submission,
                    kind=_submission_kind(safe_name),
                    file_url=default_storage.url(saved_name),
                    file_name=safe_name,
                    file_size=uploaded_file.size,
                )
        except Exception:
            if saved_name:
                default_storage.delete(saved_name)
            raise

        messages.success(request, "과제가 제출되었습니다.")
        return redirect("student:assignment-preview", assignment_id=assignment.id)

    return render(request, "student/submission_form.html", {
        "assignment": assignment,
        "form": form,
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
