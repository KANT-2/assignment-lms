"""
apps/tutor/ai_eval.py — 👨‍🏫 튜터B

FR-012 AI 1차 평가의 진입점. 뷰(views_review)는 이 모듈의 generate() 만 부른다.

- settings.GEMINI_API_KEY 있음 → apps.tutor.ai_gemini (실제 Gemini 호출)
- 키 없음 / Gemini 호출 실패 → apps.tutor.ai_stub (로컬 시뮬레이션)
"""
from __future__ import annotations

import logging

from django.conf import settings

from apps.core.models import Submission

from . import ai_stub
from .ai_stub import AiResult

logger = logging.getLogger(__name__)


def generate(submission: Submission) -> AiResult:
    if getattr(settings, "GEMINI_API_KEY", None):
        try:
            from .ai_gemini import generate as _gemini_generate

            return _gemini_generate(submission)
        except Exception:
            logger.exception(
                "Gemini AI 평가 실패 — 시뮬레이션으로 폴백 (submission=%s)", submission.pk
            )
    return ai_stub.generate(submission)
