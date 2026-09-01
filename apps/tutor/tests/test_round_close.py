"""
apps/tutor/grading — 회차 점수 마감 (docs/assignment-lms-round-close.md).

scope_assignments (과제 스코프) · snapshot (RoundScore 박제) · 재마감 덮어쓰기 ·
team_included 판정 · CSV 내보내기.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Assignment, Submission
from apps.tutor import grading
from apps.tutor.models import RoundScore

NOW = timezone.now()
R_START = NOW - timedelta(days=9)
R_END = NOW - timedelta(days=2)
PREV_END = NOW - timedelta(days=16)
BEFORE = R_START + timedelta(hours=1)

ROUND = SimpleNamespace(id=61, title="3차 회차")


def A(title, *, team=False, required=True, tier="MID", due=None, deleted=False):
    a = Assignment.objects.create(
        title=title, due_at=due or (R_END - timedelta(days=1)),
        is_team=team, is_required=required, weight_tier=tier, created_by=1,
    )
    if deleted:
        Assignment.all_objects.filter(pk=a.pk).update(deleted_at=NOW)
    return a


def sub(assignment, *, student=None, team=None, score=None):
    s = Submission.objects.create(
        assignment=assignment, student_id=student, team_id=team, final_score=score,
    )
    Submission.objects.filter(pk=s.pk).update(submitted_at=BEFORE)
    return s


class ScopeAssignmentsTests(TestCase):
    databases = {"default"}

    def _period(self, *a, **k):
        return (R_START, R_END)

    def test_scoped_by_round_period(self):
        A("inside")
        A("too_late", due=R_END + timedelta(days=1))
        A("too_early", due=PREV_END - timedelta(days=1))
        A("deleted", deleted=True)
        with patch("apps.tutor.grading.accounts.get_round_period", self._period), \
             patch("apps.tutor.grading.accounts.get_previous_round_end", return_value=PREV_END):
            got = {a.title for a in grading.scope_assignments(ROUND.id, now=NOW)}
        self.assertEqual(got, {"inside"})

    def test_no_period_falls_back_to_all_past_due(self):
        A("past")
        A("future", due=NOW + timedelta(days=3))
        with patch("apps.tutor.grading.accounts.get_round_period", return_value=None):
            got = {a.title for a in grading.scope_assignments(ROUND.id, now=NOW)}
        self.assertEqual(got, {"past"})

    def test_no_previous_round_no_lower_bound(self):
        A("old", due=PREV_END - timedelta(days=30))
        with patch("apps.tutor.grading.accounts.get_round_period", self._period), \
             patch("apps.tutor.grading.accounts.get_previous_round_end", return_value=None):
            got = {a.title for a in grading.scope_assignments(ROUND.id, now=NOW)}
        self.assertEqual(got, {"old"})


class SnapshotTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.ir = A("개인필수", team=False, required=True, tier="MID")
        self.tr = A("팀필수", team=True, required=True, tier="MID")
        sub(self.ir, student=11, score=90)
        sub(self.tr, team=200, score=80)
        self.students = [SimpleNamespace(id=11, name="김학생"), SimpleNamespace(id=12, name="이학생")]

    def _run(self, *, teams, assignment_ids=None):
        with patch("apps.tutor.grading.accounts.get_students", return_value=self.students), \
             patch("apps.tutor.grading.accounts.get_round_period", return_value=(R_START, R_END)), \
             patch("apps.tutor.grading.accounts.get_previous_round_end", return_value=PREV_END), \
             patch("apps.tutor.grading.accounts.get_student_teams", return_value=teams):
            return grading.snapshot(ROUND, closed_by=2, assignment_ids=assignment_ids, now=NOW)

    def test_creates_one_row_per_student(self):
        res = self._run(teams={11: SimpleNamespace(id=200, name="1팀")})
        self.assertEqual(RoundScore.objects.filter(round_id=61).count(), 2)
        self.assertEqual(res.student_count, 2)
        row = RoundScore.objects.get(round_id=61, student_id=11)
        self.assertEqual(row.closed_by, 2)
        self.assertEqual(row.round_title, "3차 회차")
        self.assertEqual(row.student_name, "김학생")
        self.assertEqual(sorted(row.assignment_ids), sorted([self.ir.id, self.tr.id]))
        self.assertTrue(row.policy_snapshot)

    def test_team_included_true_when_team_exists(self):
        res = self._run(teams={11: SimpleNamespace(id=200, name="1팀")})
        self.assertTrue(res.team_included)
        self.assertTrue(RoundScore.objects.get(round_id=61, student_id=11).team_included)

    def test_team_included_false_when_no_team(self):
        res = self._run(teams={})
        self.assertFalse(res.team_included)
        # 팀 없는 학생은 팀 과제 제외 → 개인만으로 산출
        row11 = RoundScore.objects.get(round_id=61, student_id=11)
        self.assertIsNotNone(row11.total)

    def test_reclose_overwrites(self):
        first = self._run(teams={})
        self.assertFalse(first.team_included)
        old_closed_at = RoundScore.objects.get(round_id=61, student_id=11).closed_at

        second = self._run(teams={11: SimpleNamespace(id=200, name="1팀"), 12: SimpleNamespace(id=200, name="1팀")})
        self.assertEqual(RoundScore.objects.filter(round_id=61).count(), 2)  # 여전히 2행
        self.assertTrue(second.team_included)
        row = RoundScore.objects.get(round_id=61, student_id=11)
        self.assertTrue(row.team_included)
        self.assertGreaterEqual(row.closed_at, old_closed_at)

    def test_assignment_ids_filter(self):
        res = self._run(teams={11: SimpleNamespace(id=200)}, assignment_ids=[self.ir.id])
        self.assertEqual([a.id for a in res.assignments], [self.ir.id])
        row = RoundScore.objects.get(round_id=61, student_id=11)
        self.assertEqual(row.assignment_ids, [self.ir.id])

    def test_matches_compute(self):
        with patch("apps.tutor.grading.accounts.get_student_teams", return_value={11: SimpleNamespace(id=200)}):
            direct = grading.compute(
                [11], now=NOW, assignments=list(Assignment.objects.all()),
            )[11]
        self._run(teams={11: SimpleNamespace(id=200)})
        row = RoundScore.objects.get(round_id=61, student_id=11)
        self.assertEqual(row.total, direct.final)
        self.assertEqual(row.achievement, direct.achievement)


class CsvExportTests(TestCase):
    databases = {"default"}

    def test_csv_headers_and_bom(self):
        RoundScore.objects.create(
            round_id=61, round_title="3차 회차", student_id=11, student_name="김학생",
            total=72.3, team_included=False, closed_at=NOW, closed_by=2,
        )
        from django.test import RequestFactory

        from apps.tutor.views_round import round_close_csv
        req = RequestFactory().get("/x")
        req.user = SimpleNamespace(id=2, is_authenticated=True)
        with patch("apps.tutor.views_student.accounts.is_tutor", return_value=True):
            resp = round_close_csv(req, 61)
        body = resp.content.decode("utf-8-sig")
        self.assertTrue(resp.content.startswith(b"\xef\xbb\xbf"))  # BOM
        self.assertIn("student_id,student_name,round_id", body)
        self.assertIn("11,김학생,61", body)
        self.assertIn("72.3", body)
