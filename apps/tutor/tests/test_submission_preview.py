import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, Submission, SubmissionFile


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), DEV_SKIP_AUTH=True)
class TutorSubmissionPreviewTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="preview-tutor")
        self.client.force_login(self.user)
        tutor_gate = patch("apps.tutor.views_manage.accounts.is_tutor", return_value=True)
        tutor_gate.start()
        self.addCleanup(tutor_gate.stop)
        self.assignment = Assignment.objects.create(
            title="미리보기 과제",
            due_at=timezone.now() + timedelta(days=1),
            is_team=False,
            created_by=self.user.id,
        )
        self.submission = Submission.objects.create(
            assignment=self.assignment,
            student_id=11,
        )

    def _file(self, name, content):
        stored_name = default_storage.save(
            f"submissions/tests/{name}", SimpleUploadedFile(name, content)
        )
        return SubmissionFile.objects.create(
            submission=self.submission,
            kind=SubmissionFile.Kind.OTHER,
            file_url=default_storage.url(stored_name),
            file_name=name,
            file_size=len(content),
        )

    def _review(self):
        with (
            patch("apps.tutor.views_review._neighbors", return_value=(None, None, (1, 1))),
            patch(
                "apps.tutor.views_review.accounts.get_user",
                return_value=SimpleNamespace(name="김학생"),
            ),
        ):
            return self.client.get(
                reverse("tutor:submission-review", args=[self.submission.pk])
            )

    def test_review_renders_arbitrary_text_file(self):
        self._file("solution.sql", b"SELECT name, score FROM students;")

        response = self._review()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SELECT name, score FROM students;")
        self.assertContains(response, "텍스트 미리보기")

    def test_review_renders_cp949_text_file(self):
        self._file("notes.log", "한글 로그입니다".encode("cp949"))

        response = self._review()

        self.assertContains(response, "한글 로그입니다")

    def test_review_uses_inline_endpoints_for_image_and_pdf(self):
        image = self._file("diagram.png", b"\x89PNG\r\n\x1a\npreview")
        pdf = self._file("report.pdf", b"%PDF-1.4 preview")

        response = self._review()

        self.assertContains(response, reverse("tutor:submission-file-inline", args=[image.pk]))
        self.assertContains(response, reverse("tutor:submission-file-inline", args=[pdf.pk]))

        image_response = self.client.get(
            reverse("tutor:submission-file-inline", args=[image.pk])
        )
        pdf_response = self.client.get(
            reverse("tutor:submission-file-inline", args=[pdf.pk])
        )
        self.assertEqual(image_response["Content-Type"], "image/png")
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_binary_file_remains_unsupported(self):
        self._file("archive.bin", b"\x00\x01\x02\x03")

        response = self._review()

        self.assertContains(response, "미리보기 미지원")

