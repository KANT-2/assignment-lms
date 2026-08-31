from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.github_sync.models import StudentGithubAccount

from .conftest_settings import ENABLED_SETTINGS


class DashboardCardTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="d", password="pw")
        self.client.force_login(self.user)
        for target in (
            "apps.student.views_dashboard.accounts.is_student",
            "apps.common.context_processors.accounts.is_student",
        ):
            p = patch(target, return_value=True)
            p.start()
            self.addCleanup(p.stop)
        for target in (
            "apps.student.views_dashboard.accounts.is_tutor",
            "apps.common.context_processors.accounts.is_tutor",
        ):
            p = patch(target, return_value=False)
            p.start()
            self.addCleanup(p.stop)
        p = patch(
            "apps.student.views_dashboard.accounts.get_user_team", return_value=None
        )
        p.start()
        self.addCleanup(p.stop)

    def test_card_hidden_when_feature_disabled(self):
        resp = self.client.get(reverse("student:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "GitHub 백업")

    @override_settings(**ENABLED_SETTINGS)
    def test_card_shows_connect_when_no_account(self):
        resp = self.client.get(reverse("student:dashboard"))
        self.assertContains(resp, "GitHub 연결하기")

    @override_settings(**ENABLED_SETTINGS)
    def test_card_shows_connected_state(self):
        acc = StudentGithubAccount(
            student_id=self.user.id, github_user_id=1, github_login="nelson",
            repo_full_name="nelson/lms-assignments",
        )
        acc.set_token("t")
        acc.save()
        resp = self.client.get(reverse("student:dashboard"))
        self.assertContains(resp, "@nelson")
        self.assertContains(resp, "내 저장소 열기")
