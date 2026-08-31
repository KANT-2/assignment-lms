from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment
from apps.tutor.forms import AssignmentForm


class AssignmentFormFieldTests(TestCase):
    databases = {"default"}

    def _data(self, **over):
        d = {
            "title": "과제",
            "description": "설명",
            "due_at": (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "is_required": "1",
            "allow_late": "1",
            "is_team": "",
            "weight_tier": "HIGH",
            "late_penalty": "15",
        }
        d.update(over)
        return d

    def test_accepts_weight_tier_and_late_penalty(self):
        form = AssignmentForm(self._data())
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(obj.weight_tier, "HIGH")
        self.assertEqual(obj.late_penalty, 15)

    def test_blank_late_penalty_becomes_zero(self):
        form = AssignmentForm(self._data(late_penalty=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["late_penalty"], 0)

    def test_late_penalty_over_100_rejected(self):
        form = AssignmentForm(self._data(late_penalty="150"))
        self.assertFalse(form.is_valid())
        self.assertIn("late_penalty", form.errors)

    def test_new_form_defaults(self):
        form = AssignmentForm()
        self.assertEqual(form.initial["weight_tier"], Assignment.WeightTier.MID)
        self.assertEqual(form.initial["late_penalty"], 0)


@override_settings(DEV_SKIP_AUTH=True)
class AssignmentCreateViewTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tutor-a", password="pw")
        self.client.force_login(self.user)
        p = patch("apps.tutor.views_manage.accounts.is_tutor", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def test_create_persists_weight_and_penalty(self):
        resp = self.client.post(reverse("tutor:assignment-list"), {
            "title": "중요 과제",
            "description": "설명",
            "due_at": (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "is_required": "1",
            "allow_late": "1",
            "is_team": "",
            "weight_tier": "LOW",
            "late_penalty": "5",
        })
        self.assertEqual(resp.status_code, 302)
        a = Assignment.objects.get(title="중요 과제")
        self.assertEqual(a.weight_tier, "LOW")
        self.assertEqual(a.late_penalty, 5)
