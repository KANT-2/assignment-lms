"""학생 A — 과제 목록, 개인 과제 제출, 제출 파일 미리보기."""

from functools import wraps
from pathlib import Path
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import transaction
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
    submissions = {
        item.assignment_id: item
        for item in Submission.objects.filter(student_id=student_id, team_id__isnull=True)
    }
    now = timezone.now()
    rows = []
    for assignment in Assignment.objects.all().order_by("due_at"):
        submission = submissions.get(assignment.id) if not assignment.is_team else None
        if assignment.is_team:
            status, status_class = "팀 과제 · 개인 제출 불가", "secondary"
        elif submission and submission.final_score is not None:
            status, status_class = "평가완료", "primary"
        elif submission:
            status, status_class = "제출완료", "success"
        elif assignment.due_at < now and not assignment.allow_late:
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
                not assignment.is_team
                and submission is None
                and (assignment.allow_late or assignment.due_at >= now)
            ),
            "due_date_str": timezone.localtime(assignment.due_at).strftime('%Y-%m-%d'),
        })
    return render(request, "student/assignment_list.html", {"rows": rows})


@student_required
def assignment_submit(request, assignment_id):
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    student_id = request.user.id

    if assignment.is_team:
        messages.error(request, "팀 과제는 개인 제출 화면에서 제출할 수 없습니다.")
        return redirect("student:assignment-list")
    if timezone.now() > assignment.due_at and not assignment.allow_late:
        messages.error(request, "마감되어 더 이상 제출할 수 없는 과제입니다.")
        return redirect("student:assignment-list")

    existing = Submission.objects.filter(
        assignment=assignment, student_id=student_id, team_id__isnull=True
    ).first()
    if existing:
        messages.info(request, "이미 제출한 과제입니다. 기존 제출물을 확인해 주세요.")
        return redirect("student:assignment-preview", assignment_id=assignment.id)

    form = SubmissionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded_file = form.cleaned_data["file"]
        safe_name = Path(uploaded_file.name).name
        storage_name = f"submissions/{student_id}/{uuid4().hex}_{safe_name}"
        saved_name = None
        try:
            with transaction.atomic():
                saved_name = default_storage.save(storage_name, uploaded_file)
                submission = Submission.objects.create(
                    assignment=assignment,
                    student_id=student_id,
                    team_id=None,
                    description=form.cleaned_data["description"],
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
    if assignment.is_team:
        raise PermissionDenied("팀 과제 제출물은 이 화면에서 볼 수 없습니다.")

    submission = get_object_or_404(
        Submission.objects.prefetch_related("files"),
        assignment=assignment,
        student_id=request.user.id,
        team_id__isnull=True,
    )
    return render(request, "student/submission_preview.html", {
        "assignment": assignment,
        "submission": submission,
        "previews": [_preview(file) for file in submission.files.all()],
        "can_resubmit": (
            timezone.now() < assignment.due_at and not submission.is_locked
        ),
    })
