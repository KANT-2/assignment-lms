"""
apps/common/preview.py — 공통 (학생 FR-005 / 튜터 FR-011 공용)

제출 파일 미리보기 데이터 추출. 파일은 학생 제출 시 MEDIA 스토리지에 저장되며,
여기서 다시 읽어 .py 는 Pygments 하이라이트, .ipynb 는 셀 단위로 파싱한다.

_preview(submission_file) -> dict:
    {
      "file": SubmissionFile,
      "kind": "PY" | "IPYNB" | "OTHER",
      # PY:    "highlighted" (safe html)  또는 "error"
      # IPYNB: "cells" [{type, source, outputs}]  또는 ("error" + "raw_text")
    }

렌더링(HTML 마크업)은 각 앱 템플릿이 담당한다 (학생/튜터 디자인 스코프가 달라서).

원 위치: apps/student/views_submit.py (2026-08-27 공통으로 이동 — 튜터 검토 화면도 사용).
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import Http404
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

from apps.core.models import SubmissionFile


def _submission_kind(file_name):
    extension = Path(file_name).suffix.lower()
    if extension == ".py":
        return SubmissionFile.Kind.PY
    if extension == ".ipynb":
        return SubmissionFile.Kind.IPYNB
    return SubmissionFile.Kind.OTHER


def _storage_name(file_url):
    if file_url.startswith(settings.MEDIA_URL):
        return file_url[len(settings.MEDIA_URL):].lstrip("/")
    raise Http404("제출 파일을 찾을 수 없습니다.")


def _read_text(submission_file):
    try:
        with default_storage.open(_storage_name(submission_file.file_url), "rb") as stored:
            return stored.read().decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError, Http404):
        # 파일이 없거나 · 스토리지 밖 URL 이거나 · 텍스트가 아니면 미리보기 생략 (페이지는 정상)
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
