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


class ScoreLockTests(TestCase):
    """scored_assignment_ids / score_locked_close — 학생 뷰의 '점수 미반영' 경고 판정."""

    databases = {"default"}

    def _close(self, *assignments, round_id=61):
        """assignments 를 집계한 RoundScore 스냅샷 1행을 만든다."""
        RoundScore.objects.create(
            round_id=round_id, student_id=11, total=50.0, closed_at=NOW, closed_by=2,
            assignment_ids=[a.id for a in assignments],
        )

    def test_no_closed_rounds(self):
        self.assertEqual(grading.scored_assignment_ids(), set())
        self.assertFalse(grading.score_locked_close(A("x")))

    def test_locked_when_assignment_in_a_snapshot(self):
        a = A("scored")
        self._close(a)
        self.assertEqual(grading.scored_assignment_ids(), {a.id})
        self.assertTrue(grading.score_locked_close(a))

    def test_not_locked_for_gap_assignment_never_snapshotted(self):
        scored = A("scored")
        gap = A("gap")
        self._close(scored)  # gap 은 집계 안 됨
        self.assertFalse(grading.score_locked_close(gap))

    def test_not_locked_when_tutor_excluded_it_at_close(self):
        included = A("included")
        excluded = A("excluded")
        self._close(included)  # excluded 는 assignment_ids 에 없음
        self.assertFalse(grading.score_locked_close(excluded))

    def test_scored_ids_unions_across_rounds(self):
        a1, a2 = A("r61"), A("r62")
        self._close(a1, round_id=61)
        self._close(a2, round_id=62)
        self.assertEqual(grading.scored_assignment_ids(), {a1.id, a2.id})


class MultiRoundAccumulationTests(TestCase):
    """회차가 마감된 뒤 새 회차가 시작될 때 점수가 회차별로 독립 누적되는지."""

    databases = {"default"}

    PREV_61 = NOW - timedelta(days=40)
    START_61 = NOW - timedelta(days=35)
    END_61 = NOW - timedelta(days=20)
    START_62 = NOW - timedelta(days=10)
    END_62 = NOW + timedelta(days=5)

    R61 = SimpleNamespace(id=61, title="3차")
    R62 = SimpleNamespace(id=62, title="4차")

    def _periods(self, round_id=None):
        return {61: (self.START_61, self.END_61), 62: (self.START_62, self.END_62)}[round_id]

    def _prev_end(self, round_id=None):
        return {61: self.PREV_61, 62: self.END_61}[round_id]

    def _mk(self, title, due, *, required=True):
        return Assignment.objects.create(
            title=title, due_at=due, is_team=False, is_required=required,
            weight_tier="MID", created_by=1,
        )

    def _sub(self, a, student, score, submitted_at):
        s = Submission.objects.create(assignment=a, student_id=student, final_score=score)
        Submission.objects.filter(pk=s.pk).update(submitted_at=submitted_at)
        return s

    def _snapshot(self, round_obj, students):
        with patch("apps.tutor.grading.accounts.get_students", return_value=students), \
             patch("apps.tutor.grading.accounts.get_round_period", side_effect=self._periods), \
             patch("apps.tutor.grading.accounts.get_previous_round_end", side_effect=self._prev_end), \
             patch("apps.tutor.grading.accounts.get_student_teams", return_value={}):
            return grading.snapshot(round_obj, closed_by=2, now=NOW)

    def _scope(self, round_id):
        with patch("apps.tutor.grading.accounts.get_round_period", side_effect=self._periods), \
             patch("apps.tutor.grading.accounts.get_previous_round_end", side_effect=self._prev_end):
            return {a.title for a in grading.scope_assignments(round_id, now=NOW)}

    def setUp(self):
        self.students = [SimpleNamespace(id=11, name="김학생")]

    def test_gap_assignment_does_not_land_in_closed_round(self):
        x = self._mk("X-회차61", self.END_61 - timedelta(days=2))
        self._sub(x, 11, 90, self.END_61 - timedelta(days=3))
        self._snapshot(self.R61, self.students)
        row_before = RoundScore.objects.get(round_id=61, student_id=11)

        # gap 에 과제 생성 + 제출
        g = self._mk("G-gap", self.END_61 + timedelta(days=3))
        self._sub(g, 11, 100, self.END_61 + timedelta(days=4))

        self.assertNotIn("G-gap", self._scope(61))
        self._snapshot(self.R61, self.students)  # 재마감
        row_after = RoundScore.objects.get(round_id=61, student_id=11)
        self.assertEqual(row_after.total, row_before.total)
        self.assertEqual(sorted(row_after.assignment_ids), [x.id])

    def test_late_submission_to_closed_round_assignment_is_orphaned(self):
        x = self._mk("X-회차61", self.END_61 - timedelta(days=2))
        self._snapshot(self.R61, self.students)  # X 미제출 상태로 마감
        locked_total = RoundScore.objects.get(round_id=61, student_id=11).total

        # 회차 62 가 current — 학생이 X 를 지각 제출
        self._sub(x, 11, 80, NOW - timedelta(days=2))

        self.assertNotIn("X-회차61", self._scope(62))
        self._snapshot(self.R62, self.students)
        self.assertFalse(
            RoundScore.objects.filter(round_id=62, student_id=11)
            .first().assignment_ids
        )
        self.assertEqual(
            RoundScore.objects.get(round_id=61, student_id=11).total, locked_total
        )

    def test_new_round_accumulates_from_its_own_scope(self):
        x = self._mk("X-회차61", self.END_61 - timedelta(days=2))
        self._sub(x, 11, 90, self.END_61 - timedelta(days=3))
        self._snapshot(self.R61, self.students)
        r61_rows_before = RoundScore.objects.filter(round_id=61).count()
        r61_total_before = RoundScore.objects.get(round_id=61, student_id=11).total

        g = self._mk("G-gap", self.END_61 + timedelta(days=3))
        h = self._mk("H-회차62", self.START_62 + timedelta(days=2))
        self._sub(g, 11, 70, self.END_61 + timedelta(days=4))
        self._sub(h, 11, 60, self.START_62 + timedelta(days=3))

        self.assertEqual(self._scope(62), {"G-gap", "H-회차62"})
        self._snapshot(self.R62, self.students)

        r62 = RoundScore.objects.get(round_id=62, student_id=11)
        self.assertEqual(sorted(r62.assignment_ids), sorted([g.id, h.id]))
        with patch("apps.tutor.grading.accounts.get_student_teams", return_value={}), \
             patch("apps.tutor.grading.accounts.get_round_period", side_effect=self._periods), \
             patch("apps.tutor.grading.accounts.get_previous_round_end", side_effect=self._prev_end):
            direct = grading.compute(
                [11], now=NOW, assignments=grading.scope_assignments(62, now=NOW)
            )[11]
        self.assertEqual(r62.total, direct.final)
        # 회차 61 스냅샷은 그대로
        self.assertEqual(RoundScore.objects.filter(round_id=61).count(), r61_rows_before)
        self.assertEqual(
            RoundScore.objects.get(round_id=61, student_id=11).total, r61_total_before
        )


class PreviewStaleCountTests(TestCase):
    """_preview 의 stale_count — 마지막 마감 이후 점수가 달라진 학생 수 (재마감 유도)."""

    databases = {"default"}

    def _preview(self):
        from apps.tutor.views_round import _preview
        with patch("apps.tutor.views_round.accounts.get_students", return_value=[SimpleNamespace(id=11, name="김학생")]), \
             patch("apps.tutor.grading.accounts.get_students", return_value=[SimpleNamespace(id=11, name="김학생")]), \
             patch("apps.tutor.grading.accounts.get_round_period", return_value=(R_START, R_END)), \
             patch("apps.tutor.views_round.accounts.get_round_period", return_value=(R_START, R_END)), \
             patch("apps.tutor.grading.accounts.get_previous_round_end", return_value=PREV_END), \
             patch("apps.tutor.grading.accounts.get_student_teams", return_value={}):
            return _preview(ROUND, NOW)

    def test_zero_when_not_closed(self):
        A("개인필수")
        sub(A("과제2"), student=11, score=80)
        self.assertEqual(self._preview()["stale_count"], 0)

    def test_counts_student_whose_score_changed_after_close(self):
        a = A("개인필수")
        # 마감: 미제출 상태로 박제
        with patch("apps.tutor.grading.accounts.get_students", return_value=[SimpleNamespace(id=11, name="김학생")]), \
             patch("apps.tutor.grading.accounts.get_round_period", return_value=(R_START, R_END)), \
             patch("apps.tutor.grading.accounts.get_previous_round_end", return_value=PREV_END), \
             patch("apps.tutor.grading.accounts.get_student_teams", return_value={}):
            grading.snapshot(ROUND, closed_by=2, now=NOW)
        # 마감 후 제출·채점 → 점수 달라짐
        sub(a, student=11, score=95)
        self.assertEqual(self._preview()["stale_count"], 1)


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
