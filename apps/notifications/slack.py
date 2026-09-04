"""Slack 알림.

- `send_slack_message` / `send_slack_dm` / `send_slack_dm_ax` : 저수준 전송 (동기, 실패 시 False).
  어떤 예외도 밖으로 던지지 않는다 — accounts DB 장애로도 호출부가 500 나면 안 된다.
- `notify_channel` / `notify_dm_ax` / `notify_dm_ax_many` : 뷰에서 쓰는 진입점.
  기본은 백그라운드 스레드로 던지고 즉시 반환한다 (요청 사이클을 막지 않음).
  `settings.SLACK_NOTIFY_SYNC=True` 면 동기 실행 (테스트/CLI 용).

큐·워커 없이 스레드로 처리한다. 부트캠프 규모에선 충분하고, 트래픽이 커지면
Celery 등으로 교체 (docs/source-delivery.md known issue).
"""

import logging
import os
import threading

import requests
from django.conf import settings
from django.db import close_old_connections

from apps.accounts_client.models import SlackIdentity

logger = logging.getLogger(__name__)

SLACK_API_URL = "https://slack.com/api"


def _format_message(*, title, message="", link=""):
    text = f"*{title}*"

    if message:
        text += f"\n{message}"

    if link:
        text += f"\n<{link}|상세 보기>"

    return text


def send_slack_message(*, title, message="", link=""):
    """Slack 채널에 메시지를 전송한다. 실패 시 False (예외 없음)."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        return False

    try:
        response = requests.post(
            webhook_url,
            json={"text": _format_message(title=title, message=message, link=link)},
            timeout=5,
        )
        response.raise_for_status()
    except Exception:  # noqa: BLE001 — 알림 실패가 호출부를 막으면 안 된다
        logger.warning("send_slack_message 실패", exc_info=True)
        return False

    return True


def send_slack_dm(*, slack_user_id, title, message="", link=""):
    """Slack 사용자에게 DM을 전송한다. 실패 시 False (예외 없음)."""
    bot_token = os.getenv("SLACK_BOT_TOKEN")

    if not bot_token or not slack_user_id:
        return False

    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        open_response = requests.post(
            f"{SLACK_API_URL}/conversations.open",
            headers=headers,
            json={"users": slack_user_id},
            timeout=5,
        )

        open_response.raise_for_status()
        open_data = open_response.json()

        if not open_data.get("ok"):
            return False

        channel_id = open_data["channel"]["id"]

        message_response = requests.post(
            f"{SLACK_API_URL}/chat.postMessage",
            headers=headers,
            json={
                "channel": channel_id,
                "text": _format_message(title=title, message=message, link=link),
            },
            timeout=5,
        )

        message_response.raise_for_status()
        return message_response.json().get("ok", False)

    except Exception:  # noqa: BLE001 — 알림 실패가 호출부를 막으면 안 된다
        logger.warning("send_slack_dm 실패 (slack_user_id=%s)", slack_user_id, exc_info=True)
        return False


def send_slack_dm_ax(ax_user_id, title="알림 제목", message="", link=""):
    """AX User ID를 Slack Member ID로 변환하여 개인 DM을 전송한다. 실패 시 False (예외 없음)."""
    try:
        identity = (
            SlackIdentity.objects.filter(user_id=ax_user_id, is_active=True).first()
        )
    except Exception:  # noqa: BLE001 — accounts DB 장애로도 호출부가 500 나면 안 된다
        logger.warning("SlackIdentity 조회 실패 (ax_user_id=%s)", ax_user_id, exc_info=True)
        return False

    if not identity:
        return False

    return send_slack_dm(
        slack_user_id=identity.slack_user_id,
        title=title,
        message=message,
        link=link,
    )


# ─────────────────────────────────────────────────────────────
# 뷰용 진입점 — 기본 비동기 (요청 사이클을 막지 않음)
# ─────────────────────────────────────────────────────────────
def _dispatch(job):
    """job() 을 백그라운드 스레드에서 실행. SLACK_NOTIFY_SYNC 면 그 자리에서 실행."""

    if getattr(settings, "SLACK_NOTIFY_SYNC", False):
        try:
            job()
        except Exception:  # noqa: BLE001
            logger.exception("slack notify job 실패")
        return

    def _run():
        try:
            job()
        except Exception:  # noqa: BLE001
            logger.exception("slack notify job 실패")
        finally:
            close_old_connections()  # 이 스레드가 연 DB 커넥션 정리

    threading.Thread(target=_run, daemon=True).start()


def active_slack_user_ids(ax_user_ids):
    """주어진 ax_user_id 중 활성 Slack 연동이 있는 것만 (조회 1회, 실패 시 빈 리스트).

    독려 뷰가 "몇 명에게 실제로 보내는지" 를 응답 시점에 알려주기 위해 쓴다 —
    실제 DM(HTTP)은 여전히 백그라운드에서 돈다.
    """
    ids = [uid for uid in ax_user_ids if uid is not None]
    if not ids:
        return []
    try:
        return list(
            SlackIdentity.objects.filter(user_id__in=ids, is_active=True)
            .values_list("user_id", flat=True)
        )
    except Exception:  # noqa: BLE001
        logger.warning("SlackIdentity 일괄 조회 실패", exc_info=True)
        return []


def notify_channel(*, title, message="", link=""):
    """채널 알림을 백그라운드로 발송."""
    _dispatch(lambda: send_slack_message(title=title, message=message, link=link))


def notify_dm_ax(ax_user_id, title="알림 제목", message="", link=""):
    """AX 사용자 1명에게 DM을 백그라운드로 발송."""
    _dispatch(lambda: send_slack_dm_ax(ax_user_id, title, message, link))


def notify_dm_ax_many(ax_user_ids, title="알림 제목", message="", link=""):
    """AX 사용자 여러 명에게 DM을 백그라운드로 순차 발송 (스레드 1개)."""
    ids = [uid for uid in ax_user_ids if uid is not None]
    if not ids:
        return

    def _job():
        for uid in ids:
            send_slack_dm_ax(uid, title, message, link)

    _dispatch(_job)
