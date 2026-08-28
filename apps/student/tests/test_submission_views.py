import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, Submission, SubmissionFile


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
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

    def test_team_assignment_is_blocked(self):
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
