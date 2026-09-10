"""학생 A — 과제 목록, 개인 과제 제출, 제출 파일 미리보기."""

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
    _preview,
    _read_text,
    _storage_name,
    _submission_kind,
)
from apps.core.models import Assignment, Submission, SubmissionFile
from apps.github_sync import services as github_services
from apps.notifications.slack import notify_dm_ax

# github_fetch: 제출 링크 검증 (GitHub 단일 파일 링크만 허용)
# grading: 회차 마감 여부 조회 (score_locked_close) — 도메인 공용 모듈
from apps.tutor import github_fetch, grading

from .forms import MAX_UPLOAD_SIZE, AssignmentSubmissionForm
from .identity import external_student_id

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
        error = _github_link_error(link)
        if error:
            return uploaded_files, links, error
    return uploaded_files, links, None


def _github_link_error(link):
    """GitHub 링크면 'AI 채점 가능한 단일 파일 링크' 인지 검증. 문제 있으면 안내 문구, 없으면 None.

    - 저장소 루트 / 폴더(tree) / PR / gist → 거부 (AI 가 코드를 읽지 못함)
    - blob/raw 형태지만 비공개·404·삭제 → 거부
    - 네트워크·타임아웃 → 통과 (우리 쪽 문제로 학생을 막지 않는다)
    비 GitHub 링크(블로그·배포 URL 등)는 그대로 통과.
    """
    if not github_fetch.is_github_url(link):
        return None
    status = github_fetch.probe_github_file(link)
    if status == "not_blob":
        return (
            "GitHub 저장소·폴더 링크는 제출할 수 없습니다. 특정 파일 페이지"
            "(.../blob/... 주소)를 붙여주세요. 파일이 여러 개면 링크를 여러 개 추가하면 됩니다."
        )
    if status == "not_found":
        return (
            f"GitHub 링크를 열 수 없습니다: {link} — 공개 저장소의 파일 링크인지, "
            "주소가 정확한지 확인해주세요."
        )
    return None


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
    status_filter = request.GET.get("status", "todo")
    type_filter = request.GET.get("type", "all")
    search_query = request.GET.get("q", "").strip()[:100]
    sort = request.GET.get("sort", "deadline")
    if status_filter not in {"todo", "submitted", "feedback"}:
        status_filter = "todo"
    if type_filter not in {"all", "personal", "team"}:
        type_filter = "all"
    if sort not in {"deadline", "latest"}:
        sort = "deadline"
    submissions = {
        item.assignment_id: item for item in Submission.objects.filter(
            Q(student_id=student_id, team_id__isnull=True)
            | Q(student_id__isnull=True, team_id=team.id if team else None)
        )
    }
    now = timezone.now()
    scored_ids = grading.scored_assignment_ids()
    rows = []
    for assignment in Assignment.objects.all():
        submission = submissions.get(assignment.id)
        is_past = assignment.due_at < now
        is_late_available = bool(
            is_past and assignment.allow_late and submission is None
        )
        score_locked = grading.score_locked_close(assignment, scored_ids=scored_ids)
        if submission and submission.final_score is not None:
            tab_status = "feedback"
        elif submission:
            tab_status = "submitted"
        elif not is_past:
            tab_status = "todo"
        else:
            tab_status = "closed"

        due_local = timezone.localtime(assignment.due_at)
        days_left = (due_local.date() - timezone.localdate()).days
        rows.append({
            "assignment": assignment,
            "submission": submission,
            "tab_status": tab_status,
            "is_past": is_past,
            "is_late_available": is_late_available,
            "score_locked": score_locked,
            "days_left": days_left,
            "is_due_today": not is_past and days_left == 0,
            "can_submit": (
                submission is None
                and (not assignment.is_team or team is not None)
                and (not is_past or assignment.allow_late)
            ),
        })

    status_counts = {
        key: sum(row["tab_status"] == key for row in rows)
        for key in ("todo", "submitted", "feedback")
    }

    def matches_controls(row):
        assignment = row["assignment"]
        return (
            (type_filter == "all"
             or (type_filter == "team" and assignment.is_team)
             or (type_filter == "personal" and not assignment.is_team))
            and (not search_query or search_query.casefold() in assignment.title.casefold())
        )

    filtered_rows = [
        row
        for row in rows
        if row["tab_status"] == status_filter and matches_controls(row)
    ]
    reverse = sort == "latest"
    sort_key = (
        (lambda row: (row["assignment"].created_at, row["assignment"].id))
        if sort == "latest"
        else (lambda row: (row["assignment"].due_at, row["assignment"].id))
    )
    filtered_rows.sort(key=sort_key, reverse=reverse)

    late_rows = [row for row in rows if row["is_late_available"] and matches_controls(row)]
    late_rows.sort(key=lambda row: (row["assignment"].due_at, row["assignment"].id), reverse=True)

    page_obj = Paginator(filtered_rows, 10).get_page(request.GET.get("page"))
    page_rows = list(page_obj.object_list)
    return render(
        request,
        "student/assignment_list.html",
        {
            "rows": page_rows,
            "filtered_count": len(filtered_rows),
            "page_obj": page_obj,
            "late_rows": late_rows,
            "status_counts": status_counts,
            "status_filter": status_filter,
            "type_filter": type_filter,
            "search_query": search_query,
            "sort": sort,
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
    # 이 과제가 속한 회차의 점수가 이미 마감됐으면 제출은 되지만 회차 점수 미반영 (경고만).
    score_locked = grading.score_locked_close(assignment)
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
                "github_enabled": github_services.enabled() and not assignment.is_team,
                "score_locked": score_locked,
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

        submit_msg = (
            "과제가 지각 제출되었습니다." if submitted_late else "과제가 제출되었습니다."
        )
        notify_dm_ax(request.user.id, submit_msg, f"과제명: {assignment.title}")
        messages.success(request, submit_msg)
        return redirect("student:assignment-preview", assignment_id=assignment.id)

    return render(request, "student/submission_form.html", {
        "assignment": assignment,
        "form": form,
        "is_late": is_late,
        "score_locked": score_locked,
        "submitted_links": request.POST.getlist("links") if request.method == "POST" else [],
        "github_enabled": github_services.enabled() and not assignment.is_team,
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
