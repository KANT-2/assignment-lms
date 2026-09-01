"""
apps/tutor/ai_gemini.py — 👨‍🏫 튜터B

FR-012 AI 1차 평가 — 실제 Gemini 호출. 뷰(views_review)가 generate() 를 부른다.

- BR-008: 참고용 1차 평가. 공식 결과는 튜터 평가 기준.
- BR-009: 튜터 수동 트리거 (뷰에서 처리).
- 재생성: 호출할 때마다 새로 요청 (기존 AiEvaluation 덮어쓰기는 뷰 책임).
- 실패 시(키 미설정 / 타임아웃 / 5xx / 파싱 실패) 예외를 그대로 올린다.
  뷰가 잡아서 "AI 평가 생성에 실패했습니다" 메시지를 띄운다 (가짜 점수 저장 안 함).
- 제출물에 읽을 수 있는 코드/텍스트가 하나도 없으면 NoReadableContent 예외
  (GitHub 링크만 냈는데 접근 실패 등). 설계: docs/assignment-lms-github-link-eval.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from google import genai
from google.genai import types
from pydantic import BaseModel

from apps.common.preview import _notebook_cells, _read_text
from apps.core.models import Submission

from . import github_fetch

# 프롬프트에 실어 보낼 제출 파일 본문 길이 상한 (토큰·비용 방어)
_MAX_CHARS_PER_FILE = 15_000
_MAX_CHARS_TOTAL = 40_000

_SYSTEM_INSTRUCTION = (
    "너는 AI 부트캠프의 조교다. 학생이 제출한 과제를 채점한다.\n"
    "- 이 평가는 참고용 1차 평가이며, 공식 점수는 튜터가 최종 결정한다.\n"
    "- 0~100 사이 정수 점수를 매긴다. 과제 요구사항 충족도를 최우선으로 본다.\n"
    "- 코드/내용이 비어 있거나 과제와 무관하면 낮은 점수를 준다.\n"
    "- comment 는 한국어 2~4문장. 잘한 점과 개선점을 구체적으로, 정중하게 쓴다.\n"
    "- 학생을 특정하는 개인정보나 단정적 표현은 피한다."
)


@dataclass
class AiResult:
    score: int
    comment: str
    unreadable_links: list[str] = field(default_factory=list)  # 못 읽은 제출 링크


class NoReadableContent(Exception):
    """제출물에서 읽어낸 코드/텍스트가 하나도 없음. links = 접근 실패한 링크들."""

    def __init__(self, links: list[str] | None = None):
        self.links = links or []
        super().__init__("제출물에서 읽을 수 있는 내용이 없습니다.")


class _GeminiResult(BaseModel):
    score: int
    comment: str


def _is_link(submission_file) -> bool:
    return submission_file.file_url.startswith(("http://", "https://"))


def _notebook_to_text(raw: str) -> str:
    """.ipynb JSON → 코드/마크다운/출력만 추린 텍스트. 파싱 실패 시 원문."""
    cells = _notebook_cells(raw)
    if cells is None:
        return raw
    out = []
    for cell in cells:
        out.append(f"[{cell['type']} cell]\n{cell['source']}")
        for output in cell.get("outputs", []):
            out.append(f"[output]\n{output}")
    return "\n\n".join(out)


def _as_prompt_text(text: str, name: str) -> str:
    return _notebook_to_text(text) if name.lower().endswith(".ipynb") else text


def _build_prompt(submission: Submission) -> tuple[str, int, list[str]]:
    """(프롬프트, 읽어낸 자료 수, 못 읽은 링크 목록)."""
    assignment = submission.assignment
    parts = [
        f"[과제 제목]\n{assignment.title}",
        f"[과제 설명]\n{assignment.description or '(설명 없음)'}",
        f"[학생이 남긴 설명]\n{submission.description or '(없음)'}",
    ]

    budget = _MAX_CHARS_TOTAL
    read_count = 0
    unreadable_links: list[str] = []
    files = list(submission.files.all())
    if not files:
        parts.append("[제출 파일]\n(첨부 파일 없음)")

    for submission_file in files:
        name = submission_file.file_name
        link = _is_link(submission_file)

        text = _read_text(submission_file)
        if text is None and link:
            text = github_fetch.fetch_github_file(submission_file.file_url)
            if text is None:
                unreadable_links.append(submission_file.file_url)
                if github_fetch.is_github_url(submission_file.file_url):
                    reason = (
                        "GitHub 링크 확인 불가 (비공개·404·타임아웃)"
                        if github_fetch.raw_url(submission_file.file_url)
                        else "GitHub 링크 — 단일 파일(blob) 링크만 지원"
                    )
                else:
                    reason = "지원하지 않는 링크"
                parts.append(f"[링크: {submission_file.file_url}]\n({reason})")
                continue

        if text is None:
            parts.append(f"[파일: {name}]\n(텍스트 파일이 아니라 내용 생략)")
            continue

        label = f"링크: {submission_file.file_url}" if link else f"파일: {name}"
        if budget <= 0:
            parts.append(f"[{label}]\n(길이 제한으로 생략)")
            continue

        body = _as_prompt_text(text, name)
        chunk = body[:_MAX_CHARS_PER_FILE][:budget]
        budget -= len(chunk)
        read_count += 1
        truncated = "\n...(이하 생략)" if len(body) > len(chunk) else ""
        parts.append(f"[{label}]\n```\n{chunk}{truncated}\n```")

    return "\n\n".join(parts), read_count, unreadable_links


def generate(submission: Submission) -> AiResult:
    """제출물 하나에 대한 Gemini 1차 평가. 실패 시 예외를 그대로 올린다."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 가 설정되지 않았습니다.")

    prompt, read_count, unreadable_links = _build_prompt(submission)
    if read_count == 0:
        raise NoReadableContent(unreadable_links)

    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        # 워커가 오래 매달리지 않도록 (ms). 초과 시 예외 → 뷰가 "실패" 메시지.
        # 모델 혼잡 시 보통 15~20초 안에 504 가 돌아온다.
        http_options=types.HttpOptions(timeout=25_000),
    )
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_GeminiResult,
            temperature=0.3,
        ),
    )

    parsed = response.parsed
    if not isinstance(parsed, _GeminiResult):
        raise ValueError(f"Gemini 응답 파싱 실패: {response.text!r}")

    score = max(0, min(100, int(parsed.score)))
    comment = (parsed.comment or "").strip()
    if not comment:
        raise ValueError("Gemini 응답에 코멘트가 비어 있음")

    return AiResult(score=score, comment=comment, unreadable_links=unreadable_links)
