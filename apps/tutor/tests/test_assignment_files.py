"""과제 첨부 자료(AssignmentFile) — 튜터 등록/수정 + 학생 다운로드."""
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, AssignmentFile


def _due():
    return (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")


def _base(**over):
    d = {
        "title": "첨부 과제",
        "description": "설명",
        "due_at": _due(),
        "is_required": "1",
        "allow_late": "1",
        "is_team": "",
        "weight_tier": "MID",
        "late_penalty": "0",
    }
    d.update(over)
    return d


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AssignmentFileTutorTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tutor-a", password="pw")
        self.client.force_login(self.user)
        for target, ret in [
            ("apps.tutor.views_manage.accounts.is_tutor", True),
            ("apps.tutor.views_manage.accounts.get_students", []),
            ("apps.tutor.views_manage.accounts.get_teams", []),
        ]:
            p = patch(target, return_value=ret)
            p.start()
            self.addCleanup(p.stop)

    def test_create_with_files_and_links(self):
        resp = self.client.post(reverse("tutor:assignment-list"), _base(
            attach_files=[
                SimpleUploadedFile("spec.pdf", b"%PDF-1.4 x", content_type="application/pdf"),
                SimpleUploadedFile("starter.zip", b"PK\x03\x04zip"),
            ],
            attach_links=["https://drive.google.com/dataset", "  ", "not-a-url"],
        ))
        self.assertEqual(resp.status_code, 302)
        a = Assignment.objects.get(title="첨부 과제")
        files = list(a.attachments.all())
        self.assertEqual(len(files), 3)  # 2 파일 + 1 유효 링크 (빈값·형식오류 무시)
        self.assertEqual([f.order for f in files], [1, 2, 3])
        pdf = files[0]
        self.assertEqual(pdf.kind, AssignmentFile.Kind.FILE)
        self.assertEqual(pdf.file_name, "spec.pdf")
        self.assertEqual(pdf.ext, "PDF")
        self.assertTrue(files[2].is_link)
        self.assertEqual(files[2].link_url, "https://drive.google.com/dataset")

    @patch("apps.tutor.views_manage.MAX_ATTACHMENT_SIZE", 5)
    def test_oversized_file_is_skipped_with_warning(self):
        resp = self.client.post(reverse("tutor:assignment-list"), _base(
            attach_files=[SimpleUploadedFile("huge.bin", b"x" * 20)],
        ), follow=True)
        a = Assignment.objects.get(title="첨부 과제")
        self.assertEqual(a.attachments.count(), 0)
        self.assertContains(resp, "huge.bin")

    def test_edit_adds_and_deletes(self):
        a = Assignment.objects.create(title="A", description="d", due_at=timezone.now() + timedelta(days=1), created_by=self.user.id)
        keep = AssignmentFile.objects.create(assignment=a, kind="LINK", link_url="https://keep.example/x", order=1)
        drop = AssignmentFile.objects.create(assignment=a, kind="LINK", link_url="https://drop.example/y", order=2)

        resp = self.client.post(reverse("tutor:assignment-edit", args=[a.id]), _base(
            title="A", delete_attach=[str(drop.id)],
            attach_links=["https://new.example/z"],
        ))
        self.assertEqual(resp.status_code, 302)
        remaining = set(a.attachments.values_list("link_url", flat=True))
        self.assertEqual(remaining, {"https://keep.example/x", "https://new.example/z"})
        self.assertFalse(AssignmentFile.objects.filter(id=drop.id).exists())
        self.assertTrue(AssignmentFile.objects.filter(id=keep.id).exists())

    def test_duplicate_link_ignored(self):
        a = Assignment.objects.create(title="A", description="d", due_at=timezone.now() + timedelta(days=1), created_by=self.user.id)
        AssignmentFile.objects.create(assignment=a, kind="LINK", link_url="https://dup.example/x", order=1)
        self.client.post(reverse("tutor:assignment-edit", args=[a.id]), _base(
            title="A", attach_links=["https://dup.example/x"],
        ))
        self.assertEqual(a.attachments.filter(link_url="https://dup.example/x").count(), 1)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AssignmentFileDownloadTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="stu", password="pw")
        self.assignment = Assignment.objects.create(
            title="A", description="d", due_at=timezone.now() + timedelta(days=1), created_by=1
        )

    def _make_file(self):
        from django.core.files.storage import default_storage
        name = default_storage.save("assignment_files/1/x_spec.pdf", SimpleUploadedFile("spec.pdf", b"%PDF data"))
        return AssignmentFile.objects.create(
            assignment=self.assignment, kind="FILE",
            file_url=default_storage.url(name), file_name="spec.pdf", file_size=8, order=1,
        )

    def test_student_downloads_file(self):
        af = self._make_file()
        self.client.force_login(self.user)
        with patch("apps.core.views.accounts.is_student", return_value=True), \
             patch("apps.core.views.accounts.is_tutor", return_value=False):
            resp = self.client.get(reverse("core:assignment-file-download", args=[af.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_link_row_is_not_downloadable(self):
        af = AssignmentFile.objects.create(assignment=self.assignment, kind="LINK", link_url="https://x.example/y", order=1)
        self.client.force_login(self.user)
        with patch("apps.core.views.accounts.is_student", return_value=True), \
             patch("apps.core.views.accounts.is_tutor", return_value=False):
            resp = self.client.get(reverse("core:assignment-file-download", args=[af.id]))
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_redirected_to_login(self):
        af = self._make_file()
        resp = self.client.get(reverse("core:assignment-file-download", args=[af.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_non_student_non_tutor_forbidden(self):
        af = self._make_file()
        self.client.force_login(self.user)
        with patch("apps.core.views.accounts.is_student", return_value=False), \
             patch("apps.core.views.accounts.is_tutor", return_value=False):
            resp = self.client.get(reverse("core:assignment-file-download", args=[af.id]))
        self.assertEqual(resp.status_code, 403)
