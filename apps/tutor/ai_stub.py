"""
apps/tutor/ai_stub.py — 👨‍🏫 튜터B

AI 1차 평가 (FR-012) 의 **구멍**. 지금은 실제 API 호출 없이 그럴듯한 점수/코멘트를
로컬에서 시뮬레이션한다. 실제 Gemini 연동은 이 파일의 generate() 만 교체하면 된다.

- BR-009: AI 평가는 튜터가 수동으로 트리거 (자동 실행 아님)
- BR-008: AI 평가는 참고용 1차 평가. 공식 결과는 튜터 평가 기준
- 재생성 지원: 호출할 때마다 새 점수/코멘트 (기존 AiEvaluation 행을 덮어씀 — 이력 없음)
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from apps.core.models import Submission, SubmissionFile

_PY_COMMENTS = [
    "조건문을 활용한 분기 처리가 요구사항에 맞게 구현되어 있습니다. 예외 상황(음수·문자 입력 등)에 "
    "대한 처리를 추가하면 더 견고한 코드가 될 것 같습니다.",
    "핵심 로직이 간결하게 작성되어 가독성이 좋습니다. 변수명을 조금 더 구체적으로 지으면 "
    "유지보수에 도움이 될 것 같습니다.",
    "요구사항을 충실히 반영했습니다. 입력값 검증 로직을 별도 함수로 분리하면 재사용성이 좋아집니다.",
]
_NB_COMMENTS = [
    "셀 구성이 논리적인 순서로 잘 정리되어 있습니다. 마크다운 설명에서 각 단계의 목적을 조금 더 "
    "풀어 쓰면 이해하기 쉬울 것 같습니다.",
    "코드와 설명이 균형 있게 구성되어 있습니다. 실행 결과에 대한 해석을 덧붙이면 완성도가 높아집니다.",
]
_OTHER_COMMENTS = [
    "제출물이 과제 요구사항의 큰 틀을 따르고 있습니다. 세부 근거와 예시를 보강하면 좋겠습니다.",
    "전반적인 구성이 체계적입니다. 결론 부분을 조금 더 구체적으로 정리하면 좋겠습니다.",
]


@dataclass
class AiResult:
    score: int
    comment: str


def _kind_of(submission: Submission) -> str:
    first = submission.files.first()
    return first.kind if first else SubmissionFile.Kind.OTHER


def generate(submission: Submission) -> AiResult:
    """제출물 하나에 대한 AI 1차 평가(시뮬레이션)를 만든다.

    ⚠ 실제 Gemini 연동 지점 — 여기만 교체하면 됨.
       (제출 파일 내용 + 학생 설명 + 과제 설명을 프롬프트로 넘겨 점수/코멘트를 받아온다)
    """
    kind = _kind_of(submission)
    pool = {
        SubmissionFile.Kind.PY: _PY_COMMENTS,
        SubmissionFile.Kind.IPYNB: _NB_COMMENTS,
    }.get(kind, _OTHER_COMMENTS)

    score = random.randint(78, 95)
    # 지각 제출이면 살짝 감점 (시뮬레이션용 휴리스틱)
    if submission.submitted_at and submission.assignment.due_at:
        if submission.submitted_at > submission.assignment.due_at:
            score -= 4
    score = max(0, min(100, score))

    return AiResult(score=score, comment=random.choice(pool))
