import pytest


@pytest.fixture(autouse=True)
def _notify_sync(settings):
    """테스트에서는 알림·GitHub 동기화를 동기 실행한다 (스레드가 테스트 DB 밖에서 뜨는 것 방지)."""
    settings.SLACK_NOTIFY_SYNC = True
    settings.GITHUB_SYNC_SYNC = True
