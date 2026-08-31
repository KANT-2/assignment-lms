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


IMAGE_PREVIEW_EXTENSIONS = {
    ".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".webp",
}
PDF_PREVIEW_EXTENSIONS = {".pdf"}
CSV_PREVIEW_EXTENSIONS = {".csv", ".tsv"}
PREVIEW_TEXT_LIMIT = 1024 * 1024


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
            raw_bytes = stored.read()
        if _looks_binary(raw_bytes):
            return None
        for encoding in ("utf-8-sig", "cp949"):
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return None
    except (OSError, ValueError, Http404):
        # 파일이 없거나 · 스토리지 밖 URL 이거나 · 텍스트가 아니면 미리보기 생략 (페이지는 정상)
        return None


def _looks_binary(raw_bytes):
    """텍스트처럼 디코딩되는 바이너리를 미리보기로 노출하지 않는다."""
    if not raw_bytes:
        return False
    sample = raw_bytes[:8192]
    if b"\x00" in sample:
        return True
    control_count = sum(byte < 32 and byte not in (9, 10, 12, 13) for byte in sample)
    return control_count / len(sample) > 0.05


def _read_preview_text(submission_file):
    try:
        with default_storage.open(_storage_name(submission_file.file_url), "rb") as stored:
            raw_bytes = stored.read(PREVIEW_TEXT_LIMIT + 1)
    except (OSError, ValueError, Http404):
        return None, False

    truncated = len(raw_bytes) > PREVIEW_TEXT_LIMIT
    raw_bytes = raw_bytes[:PREVIEW_TEXT_LIMIT]
    if _looks_binary(raw_bytes):
        return None, truncated
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw_bytes.decode(encoding), truncated
        except UnicodeDecodeError:
            continue
    return None, truncated


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
    extension = Path(submission_file.file_name).suffix.lower()
    preview = {
        "file": submission_file,
        "kind": submission_file.kind,
        "is_image": extension in IMAGE_PREVIEW_EXTENSIONS,
        "is_pdf": extension in PDF_PREVIEW_EXTENSIONS,
        "is_csv": extension in CSV_PREVIEW_EXTENSIONS,
    }
    if preview["is_image"] or preview["is_pdf"]:
        return preview

    raw_text, truncated = _read_preview_text(submission_file)
    if raw_text is None:
        if submission_file.kind != SubmissionFile.Kind.OTHER:
            preview["error"] = "파일 내용을 읽을 수 없습니다."
    elif submission_file.kind == SubmissionFile.Kind.PY:
        # Pygments가 사용자 코드를 escape한 뒤 만든 span 태그만 렌더링한다.
        preview["highlighted"] = mark_safe(
            highlight(raw_text, PythonLexer(), HtmlFormatter(nowrap=True))
        )
    elif submission_file.kind == SubmissionFile.Kind.IPYNB:
        cells = _notebook_cells(raw_text)
        if cells is None:
            preview.update(
                error="노트북 형식을 해석하지 못해 원문으로 표시합니다.",
                raw_text=raw_text,
            )
        else:
            preview["cells"] = cells
    else:
        preview["raw_text"] = raw_text
    if raw_text is not None and truncated:
        preview["truncated"] = True
    return preview
