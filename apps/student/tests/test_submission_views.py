import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, Evaluation, Submission, SubmissionFile


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), DEV_SKIP_AUTH=True)
class SubmissionViewTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="student-a-test",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.student_gate = patch(
            "apps.student.views_submit.accounts.is_student",
            return_value=True,
        )
        self.student_gate.start()
        self.addCleanup(self.student_gate.stop)

    def assignment(self, **overrides):
        values = {
            "title": "테스트 과제",
            "description": "설명",
            "due_at": timezone.now() + timedelta(days=1),
            "is_required": True,
            "allow_late": False,
            "is_team": False,
            "created_by": 1,
        }
        values.update(overrides)
        return Assignment.objects.create(**values)

    def test_personal_submission_saves_subject_and_detected_file_kind(self):
        assignment = self.assignment()

        response = self.client.post(
            reverse("student:assignment-submit", args=[assignment.id]),
            {
                "description": "제출 설명",
                "file": SimpleUploadedFile("answer.PY", b"print('ok')"),
            },
        )

        self.assertRedirects(
            response,
            reverse("student:assignment-preview", args=[assignment.id]),
        )
        submission = Submission.objects.get(assignment=assignment)
        self.assertEqual(submission.student_id, self.user.id)
        self.assertIsNone(submission.team_id)
        self.assertEqual(submission.description, "제출 설명")
        saved_file = submission.files.get()
        self.assertEqual(saved_file.kind, SubmissionFile.Kind.PY)
        self.assertEqual(saved_file.file_name, "answer.PY")

    @patch("apps.student.views_submit.accounts.get_user_team", return_value=None)
    def test_assignment_list_filters_by_submission_status(self, _get_user_team):
        submitted_assignment = self.assignment(title="제출한 과제")
        self.assignment(title="미제출 과제")
        Submission.objects.create(
            assignment=submitted_assignment,
            student_id=self.user.id,
            team_id=None,
        )

        response = self.client.get(
            reverse("student:assignment-list"),
            {"submission": "submitted", "deadline": "all"},
        )

        self.assertContains(response, "제출한 과제")
        self.assertNotContains(response, "미제출 과제")

    @patch("apps.student.views_submit.accounts.get_user_team", return_value=None)
    def test_assignment_list_combines_unsubmitted_and_open_filters(
        self, _get_user_team
    ):
        self.assignment(title="진행 중 미제출")
        self.assignment(
            title="마감된 미제출",
            due_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.get(
            reverse("student:assignment-list"),
            {"submission": "unsubmitted", "deadline": "open"},
        )

        self.assertContains(response, "진행 중 미제출")
        self.assertNotContains(response, "마감된 미제출")

    @patch("apps.student.views_submit.accounts.get_user_team")
    def test_team_member_can_submit_once_for_the_team(self, get_user_team):
        get_user_team.return_value.id = 7
        assignment = self.assignment(is_team=True)

        response = self.client.post(
            reverse("student:assignment-submit", args=[assignment.id]),
            {
                "description": "팀 제출 설명",
                "file": SimpleUploadedFile("team.py", b"print('team')"),
            },
        )

        self.assertRedirects(
            response,
            reverse("student:assignment-preview", args=[assignment.id]),
        )
        submission = Submission.objects.get(assignment=assignment)
        self.assertIsNone(submission.student_id)
        self.assertEqual(submission.team_id, 7)

    @patch("apps.student.views_submit.accounts.get_user_team")
    def test_second_team_member_cannot_submit_again(self, get_user_team):
        get_user_team.return_value.id = 7
        assignment = self.assignment(is_team=True)
        existing = Submission.objects.create(
            assignment=assignment,
            student_id=None,
            team_id=7,
            description="먼저 제출한 내용",
        )

        response = self.client.post(
            reverse("student:assignment-submit", args=[assignment.id]),
            {
                "description": "두 번째 제출",
                "file": SimpleUploadedFile("second.py", b"print('second')"),
            },
        )

        self.assertRedirects(
            response,
            reverse("student:assignment-preview", args=[assignment.id]),
        )
        self.assertEqual(Submission.objects.filter(assignment=assignment).count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.description, "먼저 제출한 내용")

    @patch("apps.student.views_submit.accounts.get_user_team", return_value=None)
    def test_student_without_team_cannot_submit_team_assignment(self, _get_user_team):
        assignment = self.assignment(is_team=True)

        response = self.client.get(
            reverse("student:assignment-submit", args=[assignment.id])
        )

        self.assertRedirects(response, reverse("student:assignment-list"))
        self.assertFalse(Submission.objects.filter(assignment=assignment).exists())

    def test_closed_assignment_without_late_submission_is_blocked(self):
        assignment = self.assignment(due_at=timezone.now() - timedelta(minutes=1))

        response = self.client.post(
            reverse("student:assignment-submit", args=[assignment.id]),
            {
                "description": "늦은 제출",
                "file": SimpleUploadedFile("late.py", b"print('late')"),
            },
        )

        self.assertRedirects(response, reverse("student:assignment-list"))
        self.assertFalse(Submission.objects.filter(assignment=assignment).exists())

    def test_closed_assignment_is_blocked_even_if_late_submission_is_enabled(self):
        assignment = self.assignment(
            due_at=timezone.now() - timedelta(minutes=1),
            allow_late=True,
        )

        response = self.client.post(
            reverse("student:assignment-submit", args=[assignment.id]),
            {
                "description": "지각 제출 시도",
                "file": SimpleUploadedFile("late.py", b"print('late')"),
            },
        )

        self.assertRedirects(response, reverse("student:assignment-list"))
        self.assertFalse(Submission.objects.filter(assignment=assignment).exists())

    def test_student_cannot_preview_another_students_submission(self):
        assignment = self.assignment()
        Submission.objects.create(
            assignment=assignment,
            student_id=self.user.id + 100,
            team_id=None,
        )

        response = self.client.get(
            reverse("student:assignment-preview", args=[assignment.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_submission_preview_shows_tutor_feedback_after_deadline(self):
        assignment = self.assignment(
            due_at=timezone.now() - timedelta(minutes=1),
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student_id=self.user.id,
            team_id=None,
        )
        Evaluation.objects.create(
            submission=submission,
            score=93,
            feedback="꼼꼼하게 잘했습니다.",
        )

        response = self.client.get(
            reverse("student:assignment-preview", args=[assignment.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "93")
        self.assertContains(response, "꼼꼼하게 잘했습니다.")

    def test_student_can_download_own_submission_file(self):
        assignment = self.assignment()
        submission = Submission.objects.create(
            assignment=assignment,
            student_id=self.user.id,
            team_id=None,
        )
        saved_name = default_storage.save(
            "submissions/test/chapter16.ipynb",
            SimpleUploadedFile("chapter16.ipynb", b'{"cells": []}'),
        )
        submission_file = SubmissionFile.objects.create(
            submission=submission,
            kind=SubmissionFile.Kind.IPYNB,
            file_url=default_storage.url(saved_name),
            file_name="chapter16.ipynb",
            file_size=13,
        )

        response = self.client.get(
            reverse("student:submission-file-download", args=[submission_file.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("chapter16.ipynb", response.headers["Content-Disposition"])

    def test_student_cannot_download_another_students_file(self):
        assignment = self.assignment()
        submission = Submission.objects.create(
            assignment=assignment,
            student_id=self.user.id + 100,
            team_id=None,
        )
        submission_file = SubmissionFile.objects.create(
            submission=submission,
            kind=SubmissionFile.Kind.IPYNB,
            file_url="/media/submissions/other/chapter16.ipynb",
            file_name="chapter16.ipynb",
            file_size=13,
        )

        response = self.client.get(
            reverse("student:submission-file-download", args=[submission_file.id])
        )

        self.assertEqual(response.status_code, 404)
