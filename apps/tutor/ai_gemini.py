"""
apps/tutor/ai_gemini.py — 👨‍🏫 튜터B

FR-012 AI 1차 평가의 실제 Gemini 구현. ai_stub.generate() 와 동일 시그니처
(Submission -> AiResult) 라서, apps.tutor.ai_eval 이 키 유무에 따라 골라 호출한다.

- BR-008: 참고용 1차 평가. 공식 결과는 튜터 평가 기준.
- BR-009: 튜터 수동 트리거 (뷰에서 처리, 여기선 신경 안 씀).
- 재생성: 호출할 때마다 새로 요청 (기존 AiEvaluation 덮어쓰기는 뷰 책임).
"""
from __future__ import annotations

from django.conf import settings
from google import genai
from google.genai import types
from pydantic import BaseModel

from apps.common.preview import _read_text
from apps.core.models import Submission

from .ai_stub import AiResult

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


class _GeminiResult(BaseModel):
    score: int
    comment: str


def _build_prompt(submission: Submission) -> str:
    assignment = submission.assignment
    parts = [
        f"[과제 제목]\n{assignment.title}",
        f"[과제 설명]\n{assignment.description or '(설명 없음)'}",
        f"[학생이 남긴 설명]\n{submission.description or '(없음)'}",
    ]

    budget = _MAX_CHARS_TOTAL
    files = list(submission.files.all())
    if not files:
        parts.append("[제출 파일]\n(첨부 파일 없음)")

    for submission_file in files:
        text = _read_text(submission_file)
        if text is None:
            parts.append(f"[파일: {submission_file.file_name}]\n(텍스트 파일이 아니라 내용 생략)")
            continue
        if budget <= 0:
            parts.append(f"[파일: {submission_file.file_name}]\n(길이 제한으로 생략)")
            continue
        chunk = text[:_MAX_CHARS_PER_FILE][:budget]
        budget -= len(chunk)
        truncated = "\n...(이하 생략)" if len(text) > len(chunk) else ""
        parts.append(f"[파일: {submission_file.file_name}]\n```\n{chunk}{truncated}\n```")

    return "\n\n".join(parts)


def generate(submission: Submission) -> AiResult:
    """제출물 하나에 대한 Gemini 1차 평가. 실패 시 예외를 그대로 올린다
    (호출자 apps.tutor.ai_eval 이 잡아서 시뮬레이션으로 폴백)."""
    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        # 워커가 무한정 매달리지 않도록 (ms). 실패하면 ai_eval 이 시뮬레이션으로 폴백.
        http_options=types.HttpOptions(timeout=30_000),
    )
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=_build_prompt(submission),
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

    return AiResult(score=score, comment=comment)
