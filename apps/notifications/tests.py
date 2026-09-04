"""apps.notifications.slack — 방어(예외 삼킴) + 비동기 디스패치 동작."""

from unittest.mock import patch

from apps.notifications import slack

# conftest.py 의 autouse 픽스처가 SLACK_NOTIFY_SYNC=True 로 만든다 → job 이 그 자리에서 실행됨.


def test_send_slack_dm_ax_swallows_db_error():
    """SlackIdentity 조회가 터져도(accounts DB 장애) 예외 없이 False."""
    with patch.object(
        slack.SlackIdentity.objects, "filter", side_effect=Exception("db down")
    ):
        assert slack.send_slack_dm_ax(123, "제목", "내용") is False


def test_active_slack_user_ids_swallows_db_error():
    with patch.object(
        slack.SlackIdentity.objects, "filter", side_effect=Exception("db down")
    ):
        assert slack.active_slack_user_ids([1, 2, 3]) == []


def test_notify_dm_ax_many_sends_each_recipient():
    with patch.object(slack, "send_slack_dm_ax", return_value=True) as mock_dm:
        slack.notify_dm_ax_many([11, 22, 33], "제목", "내용")
    assert mock_dm.call_count == 3


def test_notify_dm_ax_many_skips_none_and_empty():
    with patch.object(slack, "send_slack_dm_ax") as mock_dm:
        slack.notify_dm_ax_many([None, None], "제목")
        slack.notify_dm_ax_many([], "제목")
    mock_dm.assert_not_called()


def test_notify_channel_dispatches_message():
    with patch.object(slack, "send_slack_message", return_value=True) as mock_msg:
        slack.notify_channel(title="새 과제", message="A1")
    mock_msg.assert_called_once()


def test_dispatch_swallows_job_exception():
    """job 이 터져도 호출부로 전파되지 않는다."""
    with patch.object(slack, "send_slack_message", side_effect=Exception("boom")):
        slack.notify_channel(title="x")  # 예외 안 남
