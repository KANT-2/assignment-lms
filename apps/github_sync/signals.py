"""
apps/github_sync/signals.py

제출 파일이 저장되면(최초 제출·재제출 모두 새 SubmissionFile 을 만든다) 트랜잭션 커밋 후
학생 GitHub 저장소로 push 를 큐잉하고 즉시 1회 시도한다.

apps/github_sync/apps.py 의 ready() 에서 import 해야 동작한다.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import SubmissionFile

from . import services

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
            services.try_sync_now(push)

    transaction.on_commit(_run)
