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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), **ENABLED_SETTINGS)
class LinkSubmissionTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.assignment = Assignment.objects.create(
            title="3주차 데이터 분석",
            due_at=timezone.now() + timedelta(days=1),
            is_team=False, created_by=1,
        )
        p = patch(
            "apps.github_sync.services.accounts.get_current_round",
            return_value=type("R", (), {"id": 7, "title": "2026 1기"})(),
        )
        p.start()
        self.addCleanup(p.stop)
        acc = StudentGithubAccount(
            student_id=STUDENT_ID, github_user_id=999, github_login="nelson",
            github_name="Nelson", repo_full_name="nelson/lms-assignments",
        )
        acc.set_token("gho_test")
        acc.save()

    def _submission_with_links(self, *links, upload=None):
        sub = Submission.objects.create(assignment=self.assignment, student_id=STUDENT_ID)
        if upload:
            saved = default_storage.save(f"submissions/x/{upload}", ContentFile(b"print(1)"))
            SubmissionFile.objects.create(
                submission=sub, kind="PY", file_url=default_storage.url(saved),
                file_name=upload, file_size=8,
            )
        for link in links:
            SubmissionFile.objects.create(
                submission=sub, kind="OTHER", file_url=link, file_name=link, file_size=0,
            )
        return sub

    @patch("apps.github_sync.services.github_api.get_file_sha", return_value=None)
    @patch("apps.github_sync.services.github_api.put_file", return_value="sha1")
    def test_blob_link_is_mirrored(self, put_file, get_sha):
        # 실제 get_file_content 를 태워 인자 순서 회귀를 막는다 (requests 만 목).
        import base64

        from apps.github_sync import github_api

        captured = {}

        class _Resp:
            status_code = 200
            content = b"x"

            def json(self):
                return {
                    "type": "file", "encoding": "base64",
                    "content": base64.b64encode(b"df = 1\n").decode(),
                }

        def _fake_request(method, url, token, **kwargs):
            captured["url"] = url
            captured["params"] = kwargs.get("params")
            return _Resp()

        sub = self._submission_with_links(
            "https://github.com/nelson/other-repo/blob/main/week3/sol.py"
        )
        with patch.object(github_api, "_request", _fake_request):
            services.sync_one(services.enqueue(sub))

        self.assertEqual(
            captured["url"],
            "https://api.github.com/repos/nelson/other-repo/contents/week3/sol.py",
        )
        self.assertEqual(captured["params"], {"ref": "main"})
        committed = [c.args[2] for c in put_file.call_args_list]
        self.assertTrue(any(p.endswith("/sol.py") for p in committed))
        sub.github_push.refresh_from_db()
        self.assertEqual(sub.github_push.state, SubmissionPush.State.SYNCED)

    @patch("apps.github_sync.services.github_api.get_file_sha", return_value=None)
    @patch("apps.github_sync.services.github_api.put_file", return_value="sha1")
    @patch("apps.github_sync.services.github_api.get_file_content")
    def test_repo_root_link_goes_to_readme_only(self, get_content, put_file, get_sha):
        sub = self._submission_with_links("https://github.com/nelson/other-repo")
        services.sync_one(services.enqueue(sub))
        get_content.assert_not_called()
        readme_call = put_file.call_args_list[0]
        self.assertTrue(readme_call.args[2].endswith("/README.md"))
        self.assertIn(b"github.com/nelson/other-repo", readme_call.args[3])
        self.assertEqual(put_file.call_count, 1)  # README 만

    @patch("apps.github_sync.services.github_api.get_file_sha", return_value=None)
    @patch("apps.github_sync.services.github_api.put_file", return_value="sha1")
    @patch("apps.github_sync.services.github_api.get_file_content",
           side_effect=GithubApiError("404 Not Found", status_code=404))
    def test_blob_link_fetch_failure_falls_back_to_link(self, get_content, put_file, get_sha):
        sub = self._submission_with_links(
            "https://github.com/nelson/other-repo/blob/main/gone.py"
        )
        services.sync_one(services.enqueue(sub))
        readme_body = put_file.call_args_list[0].args[3]
        self.assertIn(b"gone.py", readme_body)
        self.assertEqual(put_file.call_count, 1)
        sub.github_push.refresh_from_db()
        self.assertEqual(sub.github_push.state, SubmissionPush.State.SYNCED)

    @patch("apps.github_sync.services.github_api.get_file_sha", return_value=None)
    @patch("apps.github_sync.services.github_api.put_file", return_value="sha1")
    @patch("apps.github_sync.services.github_api.get_file_content", return_value=b"x\n")
    def test_upload_plus_blob_link_both_committed(self, get_content, put_file, get_sha):
        sub = self._submission_with_links(
            "https://github.com/nelson/other-repo/blob/main/b.py", upload="a.py"
        )
        services.sync_one(services.enqueue(sub))
        committed = [c.args[2] for c in put_file.call_args_list]
        self.assertTrue(any(p.endswith("/a.py") for p in committed))
        self.assertTrue(any(p.endswith("/b.py") for p in committed))


class DisabledTests(TestCase):
    databases = {"default"}

    def test_enabled_false_without_keys(self):
        with override_settings(GITHUB_OAUTH_CLIENT_ID=None):
            self.assertFalse(services.enabled())
