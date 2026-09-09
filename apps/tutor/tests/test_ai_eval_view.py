"""ai_evaluation_generate 뷰 — 링크를 못 읽었을 때 튜터에게 주는 안내 메시지."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, Submission
from apps.tutor import ai_gemini


@override_settings(DEV_SKIP_AUTH=True)
class AiEvalLinkMessageTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ai-eval-tutor")
        self.client.force_login(self.user)
        gate = patch("apps.tutor.views_manage.accounts.is_tutor", return_value=True)
        gate.start()
        self.addCleanup(gate.stop)
        get_user = patch(
            "apps.tutor.views_review.accounts.get_user",
            return_value=SimpleNamespace(name="김학생"),
        )
        get_user.start()
        self.addCleanup(get_user.stop)
        self.assignment = Assignment.objects.create(
            title="과제", due_at=timezone.now() + timedelta(days=1),
            is_team=False, created_by=self.user.id,
        )
        self.submission = Submission.objects.create(
            assignment=self.assignment, student_id=11
        )

    def _post(self):
        with patch(
            "apps.tutor.views_review._neighbors", return_value=(None, None, (1, 1))
        ):
            return self.client.post(
                reverse("tutor:submission-ai-eval", args=[self.submission.pk]),
                follow=True,
            )

    def test_repo_link_gets_actionable_message(self):
        with patch(
            "apps.tutor.views_review.ai_gemini.generate",
            side_effect=ai_gemini.NoReadableContent(["https://github.com/a/b"]),
        ):
            response = self._post()
        self.assertContains(response, "저장소·폴더 링크")
        self.assertContains(response, "blob")

    def test_unreadable_repo_link_warns_on_otherwise_ok_eval(self):
        with patch(
            "apps.tutor.views_review.ai_gemini.generate",
            return_value=ai_gemini.AiResult(
                score=70,
                comment="ok",
                unreadable_links=["https://github.com/a/b/tree/main/src"],
            ),
        ):
            response = self._post()
        self.assertContains(response, "파일 목록만 확인됩니다")
