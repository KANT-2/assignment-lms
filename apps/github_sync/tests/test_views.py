from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.github_sync.models import StudentGithubAccount

from .conftest_settings import ENABLED_SETTINGS


@override_settings(**ENABLED_SETTINGS)
class OAuthCallbackTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="stud", password="pw"
        )
        self.client.force_login(self.user)
        gate = patch(
            "apps.github_sync.views.accounts.is_student", return_value=True
        )
        gate.start()
        self.addCleanup(gate.stop)

    def test_callback_rejects_bad_state(self):
        session = self.client.session
        session["github_oauth_state"] = "expected"
        session.save()
        resp = self.client.get(
            reverse("github_sync:callback"), {"state": "wrong", "code": "c"}
        )
        self.assertRedirects(resp, reverse("student:dashboard"), fetch_redirect_response=False)
        self.assertFalse(StudentGithubAccount.objects.exists())

    @patch("apps.github_sync.views.services.sync_pending")
    @patch("apps.github_sync.views.services.backfill_student", return_value=0)
    @patch("apps.github_sync.views.github_api.get_authenticated_user",
           return_value={"id": 42, "login": "nelson", "name": "Nelson"})
    @patch("apps.github_sync.views.oauth.exchange_code",
           return_value={"access_token": "gho_x", "scope": "public_repo"})
    def test_callback_stores_account(self, exchange, gh_user, backfill, sync):
        session = self.client.session
        session["github_oauth_state"] = "s123"
        session.save()
        resp = self.client.get(
            reverse("github_sync:callback"), {"state": "s123", "code": "c"}
        )
        self.assertRedirects(resp, reverse("student:dashboard"), fetch_redirect_response=False)
        acc = StudentGithubAccount.objects.get()
        self.assertEqual(acc.github_login, "nelson")
        self.assertEqual(acc.token, "gho_x")
        backfill.assert_called_once()

    def test_connect_redirects_to_github(self):
        resp = self.client.get(reverse("github_sync:connect"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("github.com/login/oauth/authorize", resp["Location"])


class DisabledViewTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="s2", password="pw")
        self.client.force_login(self.user)

    @patch("apps.github_sync.views.accounts.is_student", return_value=True)
    def test_connect_403_when_not_configured(self, _is_student):
        resp = self.client.get(reverse("github_sync:connect"))
        self.assertEqual(resp.status_code, 403)
