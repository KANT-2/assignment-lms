"""apps/core/views.py — 공유 뷰.

과제 첨부 자료(AssignmentFile) 다운로드. 학생·튜터 공통이라 core 에 둔다.
자료 자체는 코스 공개이므로 권한은 "로그인 + 학생 또는 튜터" 까지만 본다.
"""
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from apps.accounts_client import services as accounts
from apps.common.preview import _storage_name
from apps.core.models import AssignmentFile


@login_required
def assignment_file_download(request, file_id):
    uid = request.user.id
    if not (accounts.is_student(uid) or accounts.is_tutor(uid)):
        raise PermissionDenied("접근 권한이 없습니다.")

    attachment = get_object_or_404(
        AssignmentFile, pk=file_id, kind=AssignmentFile.Kind.FILE
    )
    try:
        handle = default_storage.open(_storage_name(attachment.file_url), "rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("저장된 과제 자료를 찾을 수 없습니다.") from None

    return FileResponse(
        handle,
        as_attachment=True,
        filename=Path(attachment.file_name).name or "attachment",
    )
