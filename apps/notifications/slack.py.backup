import os

import requests


SLACK_API_URL = "https://slack.com/api"


def _format_message(*, title, message="", link=""):
    text = f"*{title}*"

    if message:
        text += f"\n{message}"

    if link:
        text += f"\n<{link}|상세 보기>"

    return text


def send_slack_message(*, title, message="", link=""):
    """Slack 채널에 메시지를 전송한다."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        return False

    try:
        response = requests.post(
            webhook_url,
            json={
                "text": _format_message(
                    title=title,
                    message=message,
                    link=link,
                )
            },
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException:
        return False

    return True


def send_slack_dm(*, slack_user_id, title, message="", link=""):
    """Slack 사용자에게 DM을 전송한다."""
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
                "text": _format_message(
                    title=title,
                    message=message,
                    link=link,
                ),
            },
            timeout=5,
        )

        message_response.raise_for_status()
        return message_response.json().get("ok", False)

    except (requests.RequestException, ValueError, KeyError, TypeError):
        return False