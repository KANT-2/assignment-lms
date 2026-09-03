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
from google.genai.errors import ServerError
from pydantic import BaseModel

from apps.common.preview import _notebook_cells, _read_text
from apps.core.models import Submission

from . import github_fetch

# 프롬프트에 실어 보낼 제출 파일 본문 길이 상한 (토큰·비용 방어)
_MAX_CHARS_PER_FILE = 15_000
_MAX_CHARS_TOTAL = 40_000

_SYSTEM_INSTRUCTION = (
    "너는 AI 부트캠프의 채점 조교다. 학생 제출물을 아래 기준으로 평가한다.\n"
    "\n"
    "[역할]\n"
    "- 참고용 1차 평가다. 공식 점수는 튜터가 최종 결정한다.\n"
    "- 관대하게 주지 않는다. 애매하면 낮은 쪽으로 본다. 95점 이상은 드물게만 준다.\n"
    "- 같은 수준의 제출물은 분량·말투와 무관하게 같은 점수가 나오도록 일관되게 채점한다.\n"
    "\n"
    "[채점 기준 — 중요도 순]\n"
    "1. 요구사항 충족(최우선): [과제 설명]의 요구사항을 항목별로 나눠 각각 충족 여부를 따진다.\n"
    "   설명에 없는 요구사항을 지어내지 않는다. [과제 설명]이 비면 일반적인 완성도·코드\n"
    "   품질만으로 평가하고 그 사실을 comment에 밝힌다.\n"
    "2. 정확성·동작: 의도대로 동작할지, 노트북 [output] 결과가 맞는지. 명백한 버그·예외는 감점.\n"
    "3. 완성도: 요구된 부분을 모두 시도했는지. 일부만 제출됐으면 제출 범위만 채점하고\n"
    "   누락은 감점 사유로 comment에 적는다.\n"
    "4. 코드 품질(보조): 가독성·구조·네이밍. 요구사항을 충족했다면 스타일만으로 크게 깎지 않는다.\n"
    "\n"
    "[점수 구간]\n"
    "90-100 요구사항 전부 충족 + 동작 정확 + 코드 깔끔\n"
    "75-89  핵심 요구사항 충족, 사소한 누락·버그·스타일 문제\n"
    "60-74  절반 이상 동작하나 요구사항 일부 미충족 또는 눈에 띄는 버그\n"
    "40-59  시도했으나 핵심 기능 미완성 또는 오류 다수\n"
    "1-39   거의 미완성 / 과제와 무관 / 실행 불가\n"
    "\n"
    "[제출물 읽기]\n"
    "- 일부 파일·링크를 읽지 못했다는 표시가 있으면 읽은 자료만으로 평가하고 그 한계를\n"
    "  comment 첫 문장에 밝힌다. \"...(이하 생략)\"으로 잘린 부분은 감점하지 말고 언급만 한다.\n"
    "- 특정 언어를 요구하는데 다른 언어로 제출됐으면 지적하되, 요구를 충족하면 그것만으로 0점 처리하지 않는다.\n"
    "- [학생이 남긴 설명]은 맥락으로만 참고하고, 학생의 자기평가가 점수를 올리게 두지 않는다.\n"
    "\n"
    "[출력]\n"
    "- requirements_check: 점수를 정하기 전에 요구사항별 충족 여부를 한국어로 짧게 정리한다(채점 근거).\n"
    "- score: 위 기준으로 매긴 0~100 정수.\n"
    "- comment: 한국어 3~5문장, 정중한 존댓말. 첫 문장은 이 점수를 준 핵심 이유, 이어서 잘한 점을\n"
    "  파일·함수·구현을 짚어 1~2문장, 개선점을 실행 가능한 조언으로 1~2문장. 제출물 자체를\n"
    "  서술한다. 학생을 단정하는 표현이나 개인정보 추정은 쓰지 않는다."
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
    # 점수 산정 전 요구사항별 충족 여부를 먼저 쓰게 해 채점 일관성을 높인다(채점 근거).
    # 저장하지 않고 프롬프트 품질용으로만 쓴다.
    requirements_check: str = ""
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


def _models() -> list[str]:
    """1순위 모델 + 폴백 모델들 (중복 제거, 순서 유지)."""
    ordered = [settings.GEMINI_MODEL, *settings.GEMINI_FALLBACK_MODELS]
    seen: dict[str, None] = {}
    for name in ordered:
        if name:
            seen.setdefault(name, None)
    return list(seen)


def _call(client, model: str, prompt: str) -> tuple[int, str]:
    """모델 1개로 채점 1회. (점수, 코멘트). 5xx 는 ServerError 로 올라간다."""
    response = client.models.generate_content(
        model=model,
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
    comment = (parsed.comment or "").strip()
    if not comment:
        raise ValueError("Gemini 응답에 코멘트가 비어 있음")
    return max(0, min(100, int(parsed.score))), comment


def generate(submission: Submission) -> AiResult:
    """제출물 하나에 대한 Gemini 1차 평가. 실패 시 예외를 그대로 올린다.

    설정 모델이 5xx(혼잡)면 GEMINI_FALLBACK_MODELS 를 순서대로 재시도하고,
    전부 실패하면 마지막 ServerError 를 올린다 (뷰가 "혼잡" 메시지).
    """
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 가 설정되지 않았습니다.")

    prompt, read_count, unreadable_links = _build_prompt(submission)
    if read_count == 0:
        raise NoReadableContent(unreadable_links)

    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        # 워커가 오래 매달리지 않도록 (ms). 폴백까지 고려해 모델당 20초.
        http_options=types.HttpOptions(timeout=20_000),
    )

    last_error: ServerError | None = None
    for model in _models():
        try:
            score, comment = _call(client, model, prompt)
        except ServerError as exc:  # 5xx (503 UNAVAILABLE / 504 DEADLINE) — 다음 모델로
            last_error = exc
            continue
        return AiResult(score=score, comment=comment, unreadable_links=unreadable_links)

    raise last_error  # 모든 모델이 혼잡
