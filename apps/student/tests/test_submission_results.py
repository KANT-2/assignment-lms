import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, Evaluation, Submission, SubmissionFile


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), DEV_SKIP_AUTH=True)
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
        self.team_lookup = patch(
            "apps.student.views_result.accounts.get_user_team", return_value=None
        )
        self.team_lookup.start()
        self.addCleanup(self.team_lookup.stop)
        # DEV_SKIP_AUTH 여부와 무관하게 "현재 로그인 사용자" 로 고정
        eid = patch(
            "apps.student.views_result.external_student_id", return_value=self.user.id
        )
        eid.start()
        self.addCleanup(eid.stop)

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

    def make_team_submission(self, *, due_at=None, team_id=42):
        assignment = Assignment.objects.create(
            title="팀 과제 테스트",
            due_at=due_at or timezone.now() + timedelta(days=1),
            is_team=True,
            allow_late=True,
            created_by=1,
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student_id=None,
            team_id=team_id,
            description="팀 기존 설명",
        )
        SubmissionFile.objects.create(
            submission=submission,
            kind=SubmissionFile.Kind.OTHER,
            file_url="/media/submissions/team-old.txt",
            file_name="team-old.txt",
            file_size=3,
        )
        return submission

    def test_team_member_can_resubmit_team_submission(self):
        submission = self.make_team_submission(team_id=42)

        with patch(
            "apps.student.views_result.accounts.get_user_team",
            return_value=SimpleNamespace(id=42),
        ):
            response = self.client.post(
                reverse("student:submission-resubmit", args=[submission.id]),
                {
                    "description": "팀 새 설명",
                    "file": SimpleUploadedFile("team-new.ipynb", b'{"cells": []}'),
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Submission.objects.count(), 1)
        submission.refresh_from_db()
        self.assertEqual(submission.description, "팀 새 설명")
        self.assertEqual(submission.files.get().file_name, "team-new.ipynb")
        self.assertIsNone(submission.student_id)
        self.assertEqual(submission.team_id, 42)
        self.assertEqual(submission.last_editor_id, self.user.id)

    def test_resubmit_denied_for_non_member_of_team(self):
        submission = self.make_team_submission(team_id=42)

        with patch(
            "apps.student.views_result.accounts.get_user_team",
            return_value=SimpleNamespace(id=99),
        ):
            response = self.client.get(
                reverse("student:submission-resubmit", args=[submission.id])
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(submission.files.get().file_name, "team-old.txt")

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
        self.assertEqual(submission.last_editor_id, self.user.id)
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

    def test_result_list_shows_closed_submission(self):
        submission = self.make_submission(
            due_at=timezone.now() - timedelta(minutes=1)
        )
        Evaluation.objects.create(submission=submission, score=88, feedback="수고했어요.")

        response = self.client.get(reverse("student:result-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "학생 B 테스트")
        self.assertContains(response, "88점")
        self.assertContains(response, "피드백 완료")

    def test_result_list_has_empty_state_without_closed_submission(self):
        response = self.client.get(reverse("student:result-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "등록된 과제가 없습니다.")

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
