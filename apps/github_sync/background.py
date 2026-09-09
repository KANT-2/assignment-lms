"""GitHub 동기화 작업을 요청 사이클 밖(백그라운드 스레드)에서 돌린다.

signals 가 트랜잭션 커밋 후 호출한다. GitHub API 가 느리거나 죽어도 학생 제출 /
튜터 평가 저장의 응답을 막지 않기 위함. 실패분은 `manage.py github_sync` 배치가 재시도한다.

`settings.GITHUB_SYNC_SYNC=True` 면 그 자리에서 동기 실행한다 (테스트/CLI).
큐·워커 없이 스레드로 — 부트캠프 규모엔 충분. 트래픽이 커지면 Celery 등으로 교체
(apps.notifications.slack 과 동일한 패턴).
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def run_in_background(job) -> None:
    """job() 을 백그라운드 스레드에서 실행하고 즉시 반환한다.

    예외는 밖으로 던지지 않는다 — 호출부(제출/평가 저장)를 절대 막지 않는다.
    """
    if getattr(settings, "GITHUB_SYNC_SYNC", False):
        try:
            job()
        except Exception:  # noqa: BLE001
            logger.exception("github 백그라운드 작업 실패 (sync)")
        return

    def _run():
        try:
            job()
        except Exception:  # noqa: BLE001
            logger.exception("github 백그라운드 작업 실패")
        finally:
            close_old_connections()  # 이 스레드가 연 DB 커넥션 정리

    threading.Thread(target=_run, daemon=True).start()
