"""accounts_client.services — 팀 기간 조회 (get_team_period)."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.accounts_client import services


@override_settings(DEV_SKIP_AUTH=True)
class GetTeamPeriodDevTests(SimpleTestCase):
    def test_dev_returns_generous_window_around_now(self):
        start, end = services.get_team_period()
        now = timezone.localtime()
        self.assertLess(start, now)
        self.assertGreater(end, now)


@override_settings(DEV_SKIP_AUTH=False)
class GetTeamPeriodRealTests(SimpleTestCase):
    def _rows(self, rows):
        qs = SimpleNamespace(
            filter=lambda **kw: SimpleNamespace(
                values_list=lambda *a: SimpleNamespace(first=lambda: rows)
            )
        )
        return qs

    def test_reads_team_start_end_as_local_datetimes(self):
        with patch.object(services, "_current_round_id", return_value=61), \
             patch("apps.accounts_client.models.RoundTeamMember.objects",
                   self._rows((date(2026, 8, 12), date(2026, 8, 20)))):
            start, end = services.get_team_period()
        self.assertEqual((start.year, start.month, start.day), (2026, 8, 12))
        self.assertEqual((end.hour, end.minute), (23, 59))
        self.assertEqual((end.year, end.month, end.day), (2026, 8, 20))

    def test_missing_dates_returns_none(self):
        with patch.object(services, "_current_round_id", return_value=61), \
             patch("apps.accounts_client.models.RoundTeamMember.objects",
                   self._rows((date(2026, 8, 12), None))):
            self.assertIsNone(services.get_team_period())

    def test_no_round_returns_none(self):
        with patch.object(services, "_current_round_id", return_value=None):
            self.assertIsNone(services.get_team_period())
