"""학생 B — 재제출(FR-006), 평가 결과 조회(FR-014)."""

from pathlib import Path
from uuid import uuid4

from django.contrib import messages
from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.models import Submission, SubmissionFile

from .forms import ResubmissionForm
from .views_submit import _preview, _storage_name, _submission_kind, student_required


def _owned_submission(submission_id, student_id, *, for_update=False):
    queryset = Submission.objects.select_related("assignment").prefetch_related("files")
    if for_update:
        queryset = queryset.select_for_update()
    return get_object_or_404(
        queryset,
        pk=submission_id,
        student_id=student_id,
        team_id__isnull=True,
    )


def _resubmission_block_reason(submission):
    if submission.assignment.is_team:
        return "팀 과제는 개인 재제출 화면에서 처리할 수 없습니다."
    if timezone.now() >= submission.assignment.due_at:
        return "재제출은 과제 마감 전까지만 가능합니다."
    if submission.is_locked or hasattr(submission, "evaluation"):
        return "튜터 평가가 등록된 제출물은 재제출할 수 없습니다."
    return None


@student_required
def resubmit(request, submission_id):
    submission = _owned_submission(submission_id, request.user.id)
    block_reason = _resubmission_block_reason(submission)
    if block_reason:
        messages.error(request, block_reason)
        return redirect("student:submission-result", submission_id=submission.id)

    form = ResubmissionForm(
        request.POST or None,
        request.FILES or None,
        initial={"description": submission.description},
    )
    if request.method == "POST" and form.is_valid():
        uploaded_file = form.cleaned_data["file"]
        safe_name = Path(uploaded_file.name).name
        new_storage_name = f"submissions/{request.user.id}/{uuid4().hex}_{safe_name}"
        saved_name = default_storage.save(new_storage_name, uploaded_file)
        old_storage_names = []
        try:
            with transaction.atomic():
                locked = _owned_submission(
                    submission_id, request.user.id, for_update=True
                )
                block_reason = _resubmission_block_reason(locked)
                if block_reason:
                    transaction.set_rollback(True)
                    default_storage.delete(saved_name)
                    messages.error(request, block_reason)
                    return redirect(
                        "student:submission-result", submission_id=locked.id
                    )

                for old_file in locked.files.all():
                    try:
                        old_storage_names.append(_storage_name(old_file.file_url))
                    except Exception:
                        pass
                locked.files.all().delete()
                locked.description = form.cleaned_data["description"]
                locked.submitted_at = timezone.now()
                locked.save(update_fields=["description", "submitted_at"])
                SubmissionFile.objects.create(
                    submission=locked,
                    kind=_submission_kind(safe_name),
                    file_url=default_storage.url(saved_name),
                    file_name=safe_name,
                    file_size=uploaded_file.size,
                )
                transaction.on_commit(
                    lambda: [default_storage.delete(name) for name in old_storage_names]
                )
        except Exception:
            default_storage.delete(saved_name)
            raise

        messages.success(request, "최신 제출물로 재제출되었습니다.")
        return redirect("student:submission-result", submission_id=submission.id)

    return render(
        request,
        "student/resubmission_form.html",
        {"submission": submission, "assignment": submission.assignment, "form": form},
    )


@student_required
def result(request, submission_id):
    submission = _owned_submission(submission_id, request.user.id)
    assignment = submission.assignment
    if timezone.now() < assignment.due_at:
        messages.info(request, "평가 결과는 과제 마감 후 확인할 수 있습니다.")
        return redirect("student:assignment-preview", assignment_id=assignment.id)

    evaluation = getattr(submission, "evaluation", None)
    ai_evaluation = getattr(submission, "ai_evaluation", None)
    return render(
        request,
        "student/result_view.html",
        {
            "assignment": assignment,
            "submission": submission,
            "evaluation": evaluation,
            "ai_evaluation": ai_evaluation,
            "previews": [_preview(file) for file in submission.files.all()],
        },
    )
