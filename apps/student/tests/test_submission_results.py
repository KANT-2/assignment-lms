import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, Evaluation, Submission, SubmissionFile


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class SubmissionResultTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="student-b-test")
        self.client.force_login(self.user)
        self.student_gate = patch(
            "apps.student.views_submit.accounts.is_student", return_value=True
        )
        self.student_gate.start()
        self.addCleanup(self.student_gate.stop)

    def make_submission(self, *, due_at=None):
        assignment = Assignment.objects.create(
            title="학생 B 테스트",
            due_at=due_at or timezone.now() + timedelta(days=1),
            is_team=False,
            allow_late=True,
            created_by=1,
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student_id=self.user.id,
            team_id=None,
            description="기존 설명",
        )
        SubmissionFile.objects.create(
            submission=submission,
            kind=SubmissionFile.Kind.OTHER,
            file_url="/media/submissions/old.txt",
            file_name="old.txt",
            file_size=3,
        )
        return submission

    def test_resubmission_overwrites_final_submission(self):
        submission = self.make_submission()

        response = self.client.post(
            reverse("student:submission-resubmit", args=[submission.id]),
            {
                "description": "새 설명",
                "file": SimpleUploadedFile("new.ipynb", b'{"cells": []}'),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Submission.objects.count(), 1)
        submission.refresh_from_db()
        self.assertEqual(submission.description, "새 설명")
        self.assertEqual(submission.files.count(), 1)
        self.assertEqual(submission.files.get().kind, SubmissionFile.Kind.IPYNB)
        self.assertEqual(submission.files.get().file_name, "new.ipynb")

    def test_resubmission_is_blocked_after_deadline(self):
        submission = self.make_submission(
            due_at=timezone.now() - timedelta(minutes=1)
        )

        response = self.client.get(
            reverse("student:submission-resubmit", args=[submission.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(submission.files.get().file_name, "old.txt")

    def test_resubmission_is_blocked_after_tutor_evaluation(self):
        submission = self.make_submission()
        Evaluation.objects.create(submission=submission, score=90, feedback="완료")

        response = self.client.get(
            reverse("student:submission-resubmit", args=[submission.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(submission.files.get().file_name, "old.txt")

    def test_result_is_visible_after_deadline(self):
        submission = self.make_submission(
            due_at=timezone.now() - timedelta(minutes=1)
        )
        Evaluation.objects.create(submission=submission, score=95, feedback="잘했습니다.")

        response = self.client.get(
            reverse("student:submission-result", args=[submission.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "95")
        self.assertContains(response, "잘했습니다.")

    def test_other_students_result_returns_404(self):
        submission = self.make_submission(
            due_at=timezone.now() - timedelta(minutes=1)
        )
        submission.student_id = self.user.id + 100
        submission.save(update_fields=["student_id"])

        response = self.client.get(
            reverse("student:submission-result", args=[submission.id])
        )

        self.assertEqual(response.status_code, 404)
