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
        # 제출 완료 시 Slack DM 발송 — 외부 accounts DB 조회 없이 no-op 처리
        slack = patch("apps.student.views_submit.send_slack_dm_ax", return_value=False)
        slack.start()
        self.addCleanup(slack.stop)

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

    def test_sql_submission_is_available_in_student_text_preview(self):
        assignment = self.assignment()
        sql = b"SELECT id, title FROM assignment ORDER BY created_at DESC;"

        response = self.client.post(
            reverse("student:assignment-submit", args=[assignment.id]),
            {
                "description": "SQL 제출",
                "file": SimpleUploadedFile("report.sql", sql),
            },
        )
        self.assertRedirects(
            response,
            reverse("student:assignment-preview", args=[assignment.id]),
        )

        preview_response = self.client.get(
            reverse("student:assignment-preview", args=[assignment.id])
        )
        self.assertContains(preview_response, "report.sql")
        self.assertContains(preview_response, "SELECT id, title FROM assignment")

    def test_submission_accepts_multiple_files_and_github_link(self):
        assignment = self.assignment()

        response = self.client.post(
            reverse("student:assignment-submit", args=[assignment.id]),
            {
                "description": "복수 자료 제출",
                "files": [
                    SimpleUploadedFile("first.txt", b"first"),
                    SimpleUploadedFile("second.sql", b"SELECT 2;"),
                ],
                "links": ["https://github.com/example/assignment"],
            },
        )

        self.assertRedirects(
            response,
            reverse("student:assignment-preview", args=[assignment.id]),
        )
        submission = Submission.objects.get(assignment=assignment)
        self.assertEqual(submission.files.count(), 3)
        self.assertSetEqual(
            set(submission.files.values_list("file_name", flat=True)),
            {
                "first.txt",
                "second.sql",
                "https://github.com/example/assignment",
            },
        )

        preview_response = self.client.get(
            reverse("student:assignment-preview", args=[assignment.id])
        )
        self.assertContains(preview_response, "링크 열기")
        self.assertContains(preview_response, "https://github.com/example/assignment")

    def test_submission_accepts_non_github_web_link(self):
        assignment = self.assignment()

        response = self.client.post(
            reverse("student:assignment-submit", args=[assignment.id]),
            {"links": ["https://example.com/reference"]},
        )

        self.assertRedirects(
            response,
            reverse("student:assignment-preview", args=[assignment.id]),
        )
        submission = Submission.objects.get(assignment=assignment)
        self.assertTrue(
            submission.files.filter(file_url="https://example.com/reference").exists()
        )

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

    @patch("apps.student.views_submit.accounts.get_user_team", return_value=None)
    def test_assignment_list_paginates_after_ten_items(self, _get_user_team):
        for number in range(1, 12):
            self.assignment(title=f"페이지 과제 {number}")

        first_page = self.client.get(reverse("student:assignment-list"))
        second_page = self.client.get(
            reverse("student:assignment-list"),
            {"page": 2},
        )

        self.assertEqual(len(first_page.context["rows"]), 10)
        self.assertEqual(len(second_page.context["rows"]), 1)
        self.assertEqual(first_page.context["page_obj"].paginator.num_pages, 2)

    @patch("apps.student.views_submit.accounts.get_user_team", return_value=None)
    def test_assignment_list_sorts_closed_then_recently_created_open_assignments(
        self, _get_user_team
    ):
        now = timezone.now()
        older_closed = self.assignment(
            title="이전 마감 과제",
            due_at=now - timedelta(days=2),
        )
        recent_closed = self.assignment(
            title="최근 마감 과제",
            due_at=now - timedelta(days=1),
        )
        older_open = self.assignment(
            title="먼저 생성된 진행 과제",
            due_at=now + timedelta(days=3),
        )
        recent_open = self.assignment(
            title="최근 생성된 진행 과제",
            due_at=now + timedelta(days=1),
        )
        Assignment.objects.filter(pk=older_open.pk).update(
            created_at=now - timedelta(hours=2)
        )
        Assignment.objects.filter(pk=recent_open.pk).update(
            created_at=now - timedelta(hours=1)
        )

        response = self.client.get(reverse("student:assignment-list"))

        assignment_ids = [
            row["assignment"].id for row in response.context["rows"]
        ]
        self.assertEqual(
            assignment_ids,
            [recent_closed.id, older_closed.id, recent_open.id, older_open.id],
        )

    @patch("apps.student.views_submit.accounts.get_user_team", return_value=None)
    def test_assignment_list_groups_by_created_month(self, _get_user_team):
        assignment = self.assignment(title="생성일 묶음 과제")

        response = self.client.get(
            reverse("student:assignment-list"),
            {"date_group": "month"},
        )

        expected_month = timezone.localtime(assignment.created_at).strftime(
            "%Y년 %m월"
        )
        self.assertEqual(response.context["date_group"], "month")
        self.assertContains(response, f"진행 중 · {expected_month}")
        self.assertContains(response, "생성일 묶음 과제")

    @patch("apps.student.views_submit.accounts.get_user_team", return_value=None)
    def test_assignment_list_filters_by_selected_created_date(self, _get_user_team):
        selected = self.assignment(title="선택 날짜 과제")
        other = self.assignment(title="다른 날짜 과제")
        selected_date = timezone.localtime(selected.created_at).date()
        Assignment.objects.filter(pk=other.pk).update(
            created_at=selected.created_at - timedelta(days=1)
        )

        response = self.client.get(
            reverse("student:assignment-list"),
            {"created_date": selected_date.isoformat()},
        )

        self.assertContains(response, "선택 날짜 과제")
        self.assertNotContains(response, "다른 날짜 과제")
        self.assertEqual(response.context["created_date"], selected_date.isoformat())

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

    def test_closed_assignment_accepts_late_submission_when_enabled(self):
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

        self.assertRedirects(
            response,
            reverse("student:assignment-preview", args=[assignment.id]),
        )
        submission = Submission.objects.get(assignment=assignment)
        self.assertGreater(submission.submitted_at, assignment.due_at)
        self.assertEqual(submission.description, "지각 제출 시도")

    def test_assignment_list_offers_late_submission_when_enabled(self):
        assignment = self.assignment(
            due_at=timezone.now() - timedelta(minutes=1),
            allow_late=True,
        )

        response = self.client.get(reverse("student:assignment-list"))

        self.assertContains(response, assignment.title)
        self.assertContains(response, "지각 제출 가능")
        self.assertContains(
            response,
            reverse("student:assignment-submit", args=[assignment.id]),
        )

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

    def test_student_can_preview_own_image_inline(self):
        assignment = self.assignment()
        submission = Submission.objects.create(
            assignment=assignment,
            student_id=self.user.id,
            team_id=None,
        )
        png_bytes = b"\x89PNG\r\n\x1a\npreview"
        saved_name = default_storage.save(
            "submissions/test/preview.png",
            SimpleUploadedFile("preview.png", png_bytes, content_type="image/png"),
        )
        submission_file = SubmissionFile.objects.create(
            submission=submission,
            kind=SubmissionFile.Kind.OTHER,
            file_url=default_storage.url(saved_name),
            file_name="preview.png",
            file_size=len(png_bytes),
        )

        page_response = self.client.get(
            reverse("student:assignment-preview", args=[assignment.id])
        )
        image_response = self.client.get(
            reverse("student:submission-file-image", args=[submission_file.id])
        )

        self.assertContains(page_response, "preview.png 미리보기")
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response["Content-Type"], "image/png")
        self.assertNotIn("attachment", image_response["Content-Disposition"])

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
