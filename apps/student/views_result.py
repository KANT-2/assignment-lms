"""학생 B — 재제출(FR-006), 평가 결과 조회(FR-014)."""

from pathlib import Path
from uuid import uuid4

from django.contrib import messages
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts_client import services as accounts
from apps.core.models import Assignment, Submission, SubmissionFile
from apps.github_sync import services as github_services

from .forms import ResubmissionForm
from .identity import external_student_id
from .views_submit import (
    _preview,
    _storage_name,
    _submission_kind,
    _submitted_resources,
    student_required,
)


def _resubmittable_submission(request, submission_id, *, for_update=False):
    """재제출 대상 제출물 — 개인 과제는 본인 것, 팀 과제는 소속 팀 것.

    팀 제출물은 팀당 1행(team_id만 채움)이라, 팀원 누구나 재제출하면 전원에게 반영된다.
    """
    queryset = Submission.objects.select_related("assignment").prefetch_related("files")
    if for_update:
        queryset = queryset.select_for_update()
    owner_filter = Q(student_id=request.user.id, team_id__isnull=True)
    team = accounts.get_user_team(external_student_id(request))
    if team:
        owner_filter |= Q(student_id__isnull=True, team_id=team.id)
    return get_object_or_404(queryset, owner_filter, pk=submission_id)


def _resubmission_block_reason(submission):
    if timezone.now() >= submission.assignment.due_at:
        return "재제출은 과제 마감 전까지만 가능합니다."
    if submission.is_locked or hasattr(submission, "evaluation"):
        return "튜터 평가가 등록된 제출물은 재제출할 수 없습니다."
    return None


def _result_submission(submission_id, student_id, external_id):
    team = accounts.get_user_team(external_id)
    owner_filter = Q(student_id=student_id, team_id__isnull=True)
    if team:
        owner_filter |= Q(student_id__isnull=True, team_id=team.id)
    return get_object_or_404(
        Submission.objects.select_related(
            "assignment", "evaluation", "ai_evaluation"
        ).prefetch_related("files"),
        owner_filter,
        pk=submission_id,
    )


@student_required
def result_list(request):
    team = accounts.get_user_team(external_student_id(request))
    owner_filter = Q(student_id=request.user.id, team_id__isnull=True)
    if team:
        owner_filter |= Q(student_id__isnull=True, team_id=team.id)

    submissions = {
        submission.assignment_id: submission
        for submission in Submission.objects.filter(owner_filter).select_related(
            "evaluation", "ai_evaluation"
        )
    }
    now = timezone.now()
    rows = []
    for assignment in Assignment.objects.all().order_by("-due_at"):
        submission = submissions.get(assignment.id)
        is_past = assignment.due_at <= now
        evaluation = getattr(submission, "evaluation", None) if submission else None
        if not is_past:
            status, status_class = "마감 전", "secondary"
        elif submission is None:
            status, status_class = "제출 기록 없음", "danger"
        elif evaluation is None:
            status, status_class = "피드백 대기", "secondary"
        else:
            status, status_class = "피드백 완료", "primary"
        rows.append(
            {
                "assignment": assignment,
                "submission": submission,
                "evaluation": evaluation,
                "is_past": is_past,
                "status": status,
                "status_class": status_class,
            }
        )
    return render(
        request,
        "student/result_list.html",
        {"rows": rows},
    )


@student_required
def resubmit(request, submission_id):
    submission = _resubmittable_submission(request, submission_id)
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
        uploaded_files, links, resource_error = _submitted_resources(request)
        if resource_error:
            last_editor = (
                accounts.get_user(submission.last_editor_id)
                if submission.last_editor_id
                else None
            )
            return render(
                request,
                "student/resubmission_form.html",
                {
                    "submission": submission,
                    "assignment": submission.assignment,
                    "form": form,
                    "last_editor": last_editor,
                    "resource_error": resource_error,
                    "submitted_links": links,
                    "github_enabled": github_services.enabled() and not submission.assignment.is_team,
                },
            )

        saved_uploads = []
        try:
            for uploaded_file in uploaded_files:
                safe_name = Path(uploaded_file.name).name
                new_storage_name = (
                    f"submissions/{request.user.id}/{uuid4().hex}_{safe_name}"
                )
                saved_name = default_storage.save(new_storage_name, uploaded_file)
                saved_uploads.append((uploaded_file, safe_name, saved_name))
        except Exception:
            for _, _, saved_name in saved_uploads:
                default_storage.delete(saved_name)
            raise

        old_storage_names = []
        try:
            with transaction.atomic():
                locked = _resubmittable_submission(
                    request, submission_id, for_update=True
                )
                block_reason = _resubmission_block_reason(locked)
                if block_reason:
                    transaction.set_rollback(True)
                    for _, _, saved_name in saved_uploads:
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
                locked.last_editor_id = external_student_id(request)
                locked.save(
                    update_fields=["description", "submitted_at", "last_editor_id"]
                )
                for uploaded_file, safe_name, saved_name in saved_uploads:
                    SubmissionFile.objects.create(
                        submission=locked,
                        kind=_submission_kind(safe_name),
                        file_url=default_storage.url(saved_name),
                        file_name=safe_name,
                        file_size=uploaded_file.size,
                    )
                for link in links:
                    SubmissionFile.objects.create(
                        submission=locked,
                        kind=SubmissionFile.Kind.OTHER,
                        file_url=link,
                        file_name=link,
                        file_size=0,
                    )
                transaction.on_commit(
                    lambda: [default_storage.delete(name) for name in old_storage_names]
                )
        except Exception:
            for _, _, saved_name in saved_uploads:
                default_storage.delete(saved_name)
            raise

        messages.success(request, "최신 제출물로 재제출되었습니다.")
        return redirect("student:submission-result", submission_id=submission.id)

    last_editor = (
        accounts.get_user(submission.last_editor_id)
        if submission.last_editor_id
        else None
    )
    return render(
        request,
        "student/resubmission_form.html",
        {
            "submission": submission,
            "assignment": submission.assignment,
            "form": form,
            "last_editor": last_editor,
            "submitted_links": request.POST.getlist("links") if request.method == "POST" else [],
            "github_enabled": github_services.enabled() and not submission.assignment.is_team,
        },
    )


@student_required
def result(request, submission_id):
    submission = _result_submission(
        submission_id,
        request.user.id,
        external_student_id(request),
    )
    assignment = submission.assignment
    if timezone.now() < assignment.due_at:
        messages.info(request, "평가 결과는 과제 마감 후 확인할 수 있습니다.")
        return redirect("student:assignment-preview", assignment_id=assignment.id)

    evaluation = getattr(submission, "evaluation", None)
    ai_evaluation = getattr(submission, "ai_evaluation", None)
    last_editor = (
        accounts.get_user(submission.last_editor_id)
        if submission.last_editor_id
        else None
    )
    return render(
        request,
        "student/result_view.html",
        {
            "assignment": assignment,
            "submission": submission,
            "evaluation": evaluation,
            "ai_evaluation": ai_evaluation,
            "last_editor": last_editor,
            "previews": [_preview(file) for file in submission.files.all()],
        },
    )
