"""
apps/github_sync/signals.py

제출 파일이 저장되면(최초 제출·재제출 모두 새 SubmissionFile 을 만든다) 트랜잭션 커밋 후
학생 GitHub 저장소로 push 를 큐잉한다. 튜터 평가가 저장되면 학생 저장소에 피드백 이슈를 건다.

상태 행(SubmissionPush / FeedbackIssue)은 커밋 직후 **동기로** 만들고(빠른 INSERT — 화면
표시·배치 재시도의 근거), 실제 GitHub 호출만 백그라운드 스레드로 넘긴다(background.run_in_background).
→ GitHub 이 느려도 학생 제출 / 튜터 평가 저장 응답이 멈추지 않는다.

apps/github_sync/apps.py 의 ready() 에서 import 해야 동작한다.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import Evaluation, SubmissionFile

from . import services
from .background import run_in_background

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SubmissionFile)
def push_submission_to_github(sender, instance: SubmissionFile, created, **kwargs):
    if not created or not services.enabled():
        return

    submission = instance.submission

    def _run():
        try:
            push = services.enqueue(submission)
        except Exception:  # noqa: BLE001
            logger.exception("github enqueue 실패 (submission#%s)", submission.pk)
            return
        if push is not None:
            run_in_background(lambda: services.try_sync_now(push))

    transaction.on_commit(_run)


@receiver(post_save, sender=Evaluation)
def push_feedback_issue_to_github(sender, instance: Evaluation, **kwargs):
    """튜터 평가(신규/수정) 저장 시 학생 저장소에 피드백 이슈를 생성/갱신한다."""
    if not services.tutor_enabled():
        return

    submission = instance.submission

    def _run():
        try:
            issue = services.ensure_feedback_issue(submission)
        except Exception:  # noqa: BLE001
            logger.exception("피드백 이슈 준비 실패 (submission#%s)", submission.pk)
            return
        if issue is not None:
            run_in_background(lambda: services.sync_feedback_issue(issue))

    transaction.on_commit(_run)
