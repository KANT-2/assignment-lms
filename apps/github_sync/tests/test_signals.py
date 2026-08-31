import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import Assignment, Submission, SubmissionFile
from apps.github_sync.models import SubmissionPush

from .conftest_settings import ENABLED_SETTINGS


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), **ENABLED_SETTINGS)
class SignalTests(TestCase):
    databases = {"default"}

    def _make_file(self):
        assignment = Assignment.objects.create(
            title="과제", due_at=timezone.now() + timedelta(days=1),
            is_team=False, created_by=1,
        )
        sub = Submission.objects.create(assignment=assignment, student_id=777)
        saved = default_storage.save("submissions/x/a.py", ContentFile(b"x"))
        with self.captureOnCommitCallbacks(execute=True):
            SubmissionFile.objects.create(
                submission=sub, kind="PY",
                file_url=default_storage.url(saved), file_name="a.py", file_size=1,
            )
        return sub

    @patch("apps.github_sync.services.try_sync_now")
    def test_submission_file_enqueues_push(self, try_sync):
        sub = self._make_file()
        push = SubmissionPush.objects.get(submission=sub)
        self.assertEqual(push.state, SubmissionPush.State.PENDING)
        try_sync.assert_called_once()

    @override_settings(GITHUB_OAUTH_CLIENT_ID=None)
    def test_disabled_does_nothing(self):
        self._make_file()
        self.assertFalse(SubmissionPush.objects.exists())
