from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.github_sync.background import run_in_background


class RunInBackgroundTests(SimpleTestCase):
    @override_settings(GITHUB_SYNC_SYNC=True)
    def test_sync_mode_runs_immediately(self):
        job = Mock()
        run_in_background(job)
        job.assert_called_once()

    @override_settings(GITHUB_SYNC_SYNC=True)
    def test_sync_mode_swallows_job_exception(self):
        # 예외가 밖으로 나오면 호출부(제출/평가 저장)가 깨진다.
        run_in_background(Mock(side_effect=RuntimeError("boom")))

    @override_settings(GITHUB_SYNC_SYNC=False)
    def test_async_mode_offloads_to_thread(self):
        job = Mock()
        with patch("apps.github_sync.background.threading.Thread") as thread_cls:
            run_in_background(job)
            thread_cls.assert_called_once()
            job.assert_not_called()  # 아직 — 스레드가 돌아야 실행
            thread_cls.call_args.kwargs["target"]()  # 스레드 본문 실행
            job.assert_called_once()
