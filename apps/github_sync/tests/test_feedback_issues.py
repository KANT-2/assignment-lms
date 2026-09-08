from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import Assignment, Evaluation, Submission, SubmissionFile
from apps.github_sync import services
from apps.github_sync.github_api import GithubApiError
from apps.github_sync.models import (
    FeedbackIssue,
    StudentGithubAccount,
    SubmissionPush,
    TutorGithubAccount,
)

from .conftest_settings import ENABLED_SETTINGS

STUDENT_ID = 4321


@override_settings(**ENABLED_SETTINGS)
class FeedbackIssueTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.assignment = Assignment.objects.create(
            title="3주차 데이터 분석",
            description="pandas",
            due_at=timezone.now() + timedelta(days=1),
            is_team=False,
            created_by=1,
        )
        self.submission = Submission.objects.create(
            assignment=self.assignment, student_id=STUDENT_ID
        )
        SubmissionFile.objects.create(
            submission=self.submission, kind="PY",
            file_url="http://x/answer.py", file_name="answer.py", file_size=8,
        )
        SubmissionPush.objects.create(
            submission=self.submission,
            state=SubmissionPush.State.SYNCED,
            committed_path="2026-1/03-data/answer.py",
            commit_sha="abc123",
        )
        acc = StudentGithubAccount(
            student_id=STUDENT_ID, github_user_id=999, github_login="nelson",
            github_name="Nelson", repo_full_name="nelson/lms-assignments",
        )
        acc.set_token("gho_student")
        acc.save()

    def _tutor(self):
        t = TutorGithubAccount(
            tutor_id=1, github_user_id=1, github_login="tutorhub", github_name="Tutor",
        )
        t.set_token("gho_tutor")
        t.save()
        return t

    def _evaluate(self, score=90, feedback="좋은 분석입니다."):
        return Evaluation.objects.create(
            submission=self.submission, score=score, feedback=feedback
        )

    @patch("apps.github_sync.services.github_api.create_issue",
           return_value={"number": 7, "html_url": "https://github.com/nelson/lms-assignments/issues/7"})
    def test_creates_issue_on_first_feedback(self, create_issue):
        self._tutor()
        ev = self._evaluate()
        fi = services.enqueue_feedback_issue(self.submission)
        self.assertEqual(fi.state, FeedbackIssue.State.CREATED)
        self.assertEqual(fi.issue_number, 7)
        create_issue.assert_called_once()
        _, repo, title, body = create_issue.call_args[0]
        self.assertEqual(repo, "nelson/lms-assignments")
        self.assertIn("tree/abc123/", body)
        self.assertIn("@nelson", body)
        self.assertIn(str(ev.score), title)

    @patch("apps.github_sync.services.github_api.create_issue",
           return_value={"number": 7, "html_url": "u"})
    def test_issue_body_lists_original_links(self, create_issue):
        self._tutor()
        SubmissionFile.objects.create(
            submission=self.submission, kind="OTHER",
            file_url="https://github.com/nelson/other-repo/blob/main/x.py",
            file_name="https://github.com/nelson/other-repo/blob/main/x.py",
            file_size=0,
        )
        self._evaluate()
        services.enqueue_feedback_issue(self.submission)
        body = create_issue.call_args[0][3]
        self.assertIn("원본 링크", body)
        self.assertIn("github.com/nelson/other-repo/blob/main/x.py", body)

    @patch("apps.github_sync.services.github_api.add_issue_comment",
           return_value={"id": 1, "html_url": "u"})
    @patch("apps.github_sync.services.github_api.create_issue",
           return_value={"number": 7, "html_url": "u"})
    def test_edited_feedback_adds_comment(self, create_issue, add_comment):
        self._tutor()
        ev = self._evaluate(feedback="처음 피드백")
        services.enqueue_feedback_issue(self.submission)

        ev.feedback = "수정된 피드백"
        ev.save()
        fi = services.enqueue_feedback_issue(self.submission)
        self.assertEqual(fi.state, FeedbackIssue.State.COMMENTED)
        add_comment.assert_called_once()
        self.assertEqual(create_issue.call_count, 1)

    @patch("apps.github_sync.services.github_api.add_issue_comment")
    @patch("apps.github_sync.services.github_api.create_issue",
           return_value={"number": 7, "html_url": "u"})
    def test_unchanged_feedback_is_noop(self, create_issue, add_comment):
        self._tutor()
        self._evaluate(feedback="같은 피드백")
        services.enqueue_feedback_issue(self.submission)
        services.enqueue_feedback_issue(self.submission)
        add_comment.assert_not_called()
        self.assertEqual(create_issue.call_count, 1)

    @patch("apps.github_sync.services.github_api.create_issue")
    def test_team_assignment_is_skipped(self, create_issue):
        self._tutor()
        team_asg = Assignment.objects.create(
            title="팀 과제", due_at=timezone.now() + timedelta(days=1),
            is_team=True, created_by=1,
        )
        team_sub = Submission.objects.create(assignment=team_asg, team_id=5)
        Evaluation.objects.create(submission=team_sub, score=80, feedback="x")
        self.assertIsNone(services.enqueue_feedback_issue(team_sub))
        self.assertFalse(FeedbackIssue.objects.filter(submission=team_sub).exists())
        create_issue.assert_not_called()

    @patch("apps.github_sync.services.github_api.create_issue")
    def test_pending_when_push_not_synced(self, create_issue):
        self._tutor()
        SubmissionPush.objects.filter(submission=self.submission).update(
            state=SubmissionPush.State.PENDING
        )
        self._evaluate()
        fi = services.enqueue_feedback_issue(self.submission)
        self.assertEqual(fi.state, FeedbackIssue.State.PENDING)
        create_issue.assert_not_called()

    @patch("apps.github_sync.services.github_api.create_issue")
    def test_noop_when_tutor_not_connected(self, create_issue):
        self._evaluate()
        fi = services.enqueue_feedback_issue(self.submission)
        self.assertEqual(fi.state, FeedbackIssue.State.PENDING)
        create_issue.assert_not_called()

    @patch("apps.github_sync.services.github_api.create_issue",
           side_effect=GithubApiError("500 boom", status_code=500))
    def test_api_error_increments_attempts(self, create_issue):
        self._tutor()
        self._evaluate()
        fi = services.enqueue_feedback_issue(self.submission)
        self.assertEqual(fi.attempts, 1)
        self.assertEqual(fi.state, FeedbackIssue.State.PENDING)
        self.assertIn("boom", fi.error_message)

    @patch("apps.github_sync.services.github_api.create_issue",
           return_value={"number": 9, "html_url": "u"})
    def test_pending_retry_via_command_helper(self, create_issue):
        self._tutor()
        SubmissionPush.objects.filter(submission=self.submission).update(
            state=SubmissionPush.State.PENDING
        )
        self._evaluate()
        services.enqueue_feedback_issue(self.submission)
        create_issue.assert_not_called()

        SubmissionPush.objects.filter(submission=self.submission).update(
            state=SubmissionPush.State.SYNCED
        )
        result = services.sync_pending_feedback_issues()
        self.assertEqual(result["created"], 1)
        create_issue.assert_called_once()

    @patch("apps.github_sync.services.github_api.create_issue",
           return_value={"number": 7, "html_url": "u"})
    def test_signal_triggers_on_commit(self, create_issue):
        self._tutor()
        with self.captureOnCommitCallbacks(execute=True):
            Evaluation.objects.create(
                submission=self.submission, score=88, feedback="시그널 테스트"
            )
        self.assertTrue(
            FeedbackIssue.objects.filter(
                submission=self.submission, state=FeedbackIssue.State.CREATED
            ).exists()
        )
