import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import Assignment, Submission, SubmissionFile
from apps.github_sync import services
from apps.github_sync.github_api import GithubApiError
from apps.github_sync.models import StudentGithubAccount, SubmissionPush

from .conftest_settings import ENABLED_SETTINGS

STUDENT_ID = 4321


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), **ENABLED_SETTINGS)
class ServiceTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.assignment = Assignment.objects.create(
            title="3주차 데이터 분석",
            description="pandas 로 분석",
            due_at=timezone.now() + timedelta(days=1),
            is_team=False,
            created_by=1,
        )
        p = patch(
            "apps.github_sync.services.accounts.get_current_round",
            return_value=type("R", (), {"id": 7, "title": "2026 1기"})(),
        )
        p.start()
        self.addCleanup(p.stop)

    def _submission(self, *, student_id=STUDENT_ID, team_id=None, name="answer.py"):
        sub = Submission.objects.create(
            assignment=self.assignment, student_id=student_id, team_id=team_id
        )
        saved = default_storage.save(f"submissions/x/{name}", ContentFile(b"print(1)"))
        SubmissionFile.objects.create(
            submission=sub, kind="PY",
            file_url=default_storage.url(saved), file_name=name, file_size=8,
        )
        return sub

    def _account(self):
        acc = StudentGithubAccount(
            student_id=STUDENT_ID, github_user_id=999, github_login="nelson",
            github_name="Nelson", repo_full_name="nelson/lms-assignments",
        )
        acc.set_token("gho_test")
        acc.save()
        return acc

    # --- enqueue ---
    def test_enqueue_personal_creates_pending(self):
        push = services.enqueue(self._submission())
        self.assertEqual(push.state, SubmissionPush.State.PENDING)

    def test_enqueue_team_submission_is_ignored(self):
        team_sub = self._submission(student_id=None, team_id=55)
        self.assertIsNone(services.enqueue(team_sub))
        self.assertFalse(SubmissionPush.objects.exists())

    def test_enqueue_resets_synced_to_pending(self):
        push = services.enqueue(self._submission())
        push.state = SubmissionPush.State.SYNCED
        push.save()
        again = services.enqueue(push.submission)
        self.assertEqual(again.state, SubmissionPush.State.PENDING)

    # --- sync_one ---
    def test_sync_one_without_account_marks_no_account(self):
        push = services.enqueue(self._submission())
        services.sync_one(push)
        push.refresh_from_db()
        self.assertEqual(push.state, SubmissionPush.State.NO_ACCOUNT)

    @patch("apps.github_sync.services.github_api.put_file", return_value="commitsha")
    @patch("apps.github_sync.services.github_api.get_file_sha", return_value=None)
    @patch("apps.github_sync.services.github_api.ensure_repo",
           return_value="nelson/lms-assignments")
    def test_sync_one_success(self, ensure_repo, get_sha, put_file):
        self._account()
        push = services.enqueue(self._submission())
        services.sync_one(push)
        push.refresh_from_db()
        self.assertEqual(push.state, SubmissionPush.State.SYNCED)
        self.assertEqual(push.commit_sha, "commitsha")
        # 경로: <round>/<id 2자리>-<제목슬러그>/<파일명>
        self.assertIn("2026-1", push.committed_path)
        self.assertTrue(push.committed_path.endswith("/answer.py"))
        # README + 파일 = 2회 커밋
        self.assertEqual(put_file.call_count, 2)

    @patch("apps.github_sync.services.github_api.get_file_sha", return_value=None)
    @patch("apps.github_sync.services.github_api.put_file",
           side_effect=GithubApiError("500 boom", status_code=500))
    def test_sync_one_api_error_increments_attempts(self, put_file, get_sha):
        self._account()
        push = services.enqueue(self._submission())
        services.sync_one(push)
        push.refresh_from_db()
        self.assertEqual(push.attempts, 1)
        self.assertEqual(push.state, SubmissionPush.State.PENDING)  # < MAX_ATTEMPTS
        self.assertIn("boom", push.error_message)

    # --- finalize_due ---
    @patch("apps.github_sync.services.github_api.put_file", return_value="finalsha")
    @patch("apps.github_sync.services.github_api.get_file_sha", return_value="oldsha")
    def test_finalize_due_only_touches_past_deadline(self, get_sha, put_file):
        self._account()
        # 마감 지난 과제
        past = Assignment.objects.create(
            title="지난 과제", due_at=timezone.now() - timedelta(hours=1),
            is_team=False, created_by=1,
        )
        sub = Submission.objects.create(assignment=past, student_id=STUDENT_ID)
        default_storage.save("submissions/x/p.py", ContentFile(b"x"))
        SubmissionFile.objects.create(
            submission=sub, kind="PY",
            file_url=default_storage.url("submissions/x/p.py"),
            file_name="p.py", file_size=1,
        )
        SubmissionPush.objects.create(
            submission=sub, state=SubmissionPush.State.SYNCED
        )
        # 마감 전 과제 (finalize 대상 아님)
        future = services.enqueue(self._submission())
        future.state = SubmissionPush.State.SYNCED
        future.save()

        done = services.finalize_due(timezone.now())
        self.assertEqual(done, 1)
        sub.github_push.refresh_from_db()
        self.assertTrue(sub.github_push.is_finalized)
        future.refresh_from_db()
        self.assertFalse(future.is_finalized)

    # --- backfill ---
    def test_backfill_enqueues_existing_personal_submissions(self):
        self._submission()
        other = Assignment.objects.create(
            title="다른 과제", due_at=timezone.now() + timedelta(days=2),
            is_team=False, created_by=1,
        )
        Submission.objects.create(assignment=other, student_id=STUDENT_ID)
        count = services.backfill_student(STUDENT_ID)
        self.assertEqual(count, 2)
        self.assertEqual(SubmissionPush.objects.count(), 2)


class DisabledTests(TestCase):
    databases = {"default"}

    def test_enabled_false_without_keys(self):
        with override_settings(GITHUB_OAUTH_CLIENT_ID=None):
            self.assertFalse(services.enabled())
