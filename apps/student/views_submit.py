"""학생 A — 과제 목록, 개인 과제 제출, 제출 파일 미리보기."""

import json
from functools import wraps
from pathlib import Path
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

from apps.accounts_client import services as accounts
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


def _submission_kind(file_name):
    extension = Path(file_name).suffix.lower()
    if extension == ".py":
        return SubmissionFile.Kind.PY
    if extension == ".ipynb":
        return SubmissionFile.Kind.IPYNB
    return SubmissionFile.Kind.OTHER


def _storage_name(file_url):
    from django.conf import settings

    if file_url.startswith(settings.MEDIA_URL):
        return file_url[len(settings.MEDIA_URL):].lstrip("/")
    raise Http404("제출 파일을 찾을 수 없습니다.")


def _read_text(submission_file):
    try:
        with default_storage.open(_storage_name(submission_file.file_url), "rb") as stored:
            return stored.read().decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _notebook_cells(raw_text):
    try:
        notebook = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError):
        return None

    cells = []
    for cell in notebook.get("cells", []):
        cell_type = cell.get("cell_type", "raw")
        source_value = cell.get("source", [])
        source = "".join(source_value) if isinstance(source_value, list) else str(source_value)
        outputs = []
        if cell_type == "code":
            for output in cell.get("outputs", []):
                text = output.get("text")
                if text is None:
                    text = output.get("data", {}).get("text/plain")
                if text:
                    outputs.append("".join(text) if isinstance(text, list) else str(text))
        cells.append({"type": cell_type, "source": source, "outputs": outputs})
    return cells


def _preview(submission_file):
    preview = {"file": submission_file, "kind": submission_file.kind}
    if submission_file.kind == SubmissionFile.Kind.OTHER:
        return preview

    raw_text = _read_text(submission_file)
    if raw_text is None:
        preview["error"] = "파일 내용을 읽을 수 없습니다."
    elif submission_file.kind == SubmissionFile.Kind.PY:
        # Pygments가 사용자 코드를 escape한 뒤 만든 span 태그만 렌더링한다.
        preview["highlighted"] = mark_safe(
            highlight(raw_text, PythonLexer(), HtmlFormatter(nowrap=True))
        )
    else:
        cells = _notebook_cells(raw_text)
        if cells is None:
            preview.update(
                error="노트북 형식을 해석하지 못해 원문으로 표시합니다.",
                raw_text=raw_text,
            )
        else:
            preview["cells"] = cells
    return preview


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
