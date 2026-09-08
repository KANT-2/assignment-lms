from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.github_sync.models import TutorGithubAccount

from .conftest_settings import ENABLED_SETTINGS


@override_settings(**ENABLED_SETTINGS)
class TutorOAuthTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tut", password="pw")
        self.client.force_login(self.user)
        gate = patch("apps.github_sync.views.accounts.is_tutor", return_value=True)
        gate.start()
        self.addCleanup(gate.stop)

    def test_connect_redirects_to_github(self):
        resp = self.client.get(reverse("github_sync:tutor-connect"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("github.com/login/oauth/authorize", resp["Location"])

    def test_callback_rejects_bad_state(self):
        session = self.client.session
        session["github_oauth_state_tutor"] = "expected"
        session.save()
        resp = self.client.get(
            reverse("github_sync:tutor-callback"), {"state": "wrong", "code": "c"}
        )
        self.assertRedirects(resp, reverse("tutor:dashboard"), fetch_redirect_response=False)
        self.assertFalse(TutorGithubAccount.objects.exists())

    @patch("apps.github_sync.views.github_api.get_authenticated_user",
           return_value={"id": 5, "login": "tutorhub", "name": "Tutor"})
    @patch("apps.github_sync.views.oauth.exchange_code",
           return_value={"access_token": "gho_t", "scope": "public_repo"})
    def test_callback_stores_account(self, exchange, gh_user):
        session = self.client.session
        session["github_oauth_state_tutor"] = "s123"
        session.save()
        resp = self.client.get(
            reverse("github_sync:tutor-callback"), {"state": "s123", "code": "c"}
        )
        self.assertRedirects(resp, reverse("tutor:dashboard"), fetch_redirect_response=False)
        acc = TutorGithubAccount.objects.get()
        self.assertEqual(acc.github_login, "tutorhub")
        self.assertEqual(acc.token, "gho_t")

    def test_disconnect_removes_account(self):
        acc = TutorGithubAccount(
            tutor_id=self.user.id, github_user_id=5, github_login="tutorhub",
        )
        acc.set_token("gho_t")
        acc.save()
        resp = self.client.post(reverse("github_sync:tutor-disconnect"))
        self.assertRedirects(resp, reverse("tutor:dashboard"), fetch_redirect_response=False)
        self.assertFalse(TutorGithubAccount.objects.exists())

    def test_non_tutor_forbidden(self):
        with patch("apps.github_sync.views.accounts.is_tutor", return_value=False):
            resp = self.client.get(reverse("github_sync:tutor-connect"))
        self.assertEqual(resp.status_code, 403)


@override_settings(**ENABLED_SETTINGS)
class DashboardCardTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tutdash", password="pw", is_staff=True
        )
        self.client.force_login(self.user)
        for target in (
            "apps.tutor.views_dashboard.accounts.is_tutor",
            "apps.common.context_processors.accounts.is_tutor",
        ):
            p = patch(target, return_value=True)
            p.start()
            self.addCleanup(p.stop)
        for name, val in [
            ("get_students", [SimpleNamespace(id=1, name="학생1", email="")]),
            ("get_teams", []),
        ]:
            p = patch(f"apps.tutor.views_dashboard.accounts.{name}", return_value=val)
            p.start()
            self.addCleanup(p.stop)

    def test_card_shows_connect_when_no_account(self):
        resp = self.client.get(reverse("tutor:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "GitHub 연결하기")

    def test_card_shows_connected_state(self):
        acc = TutorGithubAccount(
            tutor_id=self.user.id, github_user_id=1, github_login="tutorhub",
        )
        acc.set_token("t")
        acc.save()
        resp = self.client.get(reverse("tutor:dashboard"))
        self.assertContains(resp, "@tutorhub")
