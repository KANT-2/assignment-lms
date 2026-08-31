from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Assignment, Submission
from apps.tutor import grading

NOW = timezone.now()
PAST = NOW - timedelta(days=1)
FUTURE = NOW + timedelta(days=1)
S = 501


def make_assignment(**over):
    d = dict(title="A", due_at=PAST, is_team=False, is_required=True,
             weight_tier="MID", late_penalty=0, created_by=1)
    d.update(over)
    return Assignment.objects.create(**d)


def submit(assignment, *, student_id=S, team_id=None, score=None, submitted_at=None):
    sub = Submission.objects.create(
        assignment=assignment, student_id=student_id, team_id=team_id, final_score=score,
    )
    if submitted_at:
        Submission.objects.filter(pk=sub.pk).update(submitted_at=submitted_at)
    return sub


class GradingTests(TestCase):
    databases = {"default"}

    def score(self, sid=S):
        return grading.compute([sid])[sid]

    # ---- 기본 ----
    def test_no_past_assignments(self):
        make_assignment(due_at=FUTURE)
        r = self.score()
        self.assertIsNone(r.final)
        self.assertIsNone(r.achievement)

    def test_single_graded_ontime(self):
        submit(make_assignment(), score=85)
        r = self.score()
        self.assertAlmostEqual(r.achievement, 85)
        self.assertAlmostEqual(r.sincerity, 100)
        self.assertEqual(r.final, round(85 * 0.7 + 100 * 0.3, 1))  # 89.5

    # ---- 과제별 점수 규칙 ----
    def test_required_missing_is_ten(self):
        make_assignment()
        r = self.score()
        self.assertAlmostEqual(r.achievement, 10)
        self.assertAlmostEqual(r.sincerity, 0)

    def test_optional_missing_is_zero(self):
        make_assignment(is_required=False)
        r = self.score()
        self.assertAlmostEqual(r.achievement, 0)

    def test_required_floor_applies(self):
        a = make_assignment()
        submit(a, score=30)
        self.assertAlmostEqual(self.score().achievement, 40)

    def test_optional_floor_applies(self):
        a = make_assignment(is_required=False)
        submit(a, score=5)
        self.assertAlmostEqual(self.score().achievement, 20)

    def test_late_penalty_deducted(self):
        a = make_assignment(late_penalty=10)
        submit(a, score=80, submitted_at=NOW)  # NOW > PAST → 지각
        self.assertAlmostEqual(self.score().achievement, 70)

    def test_late_penalty_cannot_break_floor(self):
        a = make_assignment(late_penalty=10)
        submit(a, score=45, submitted_at=NOW)  # 45-10=35 < 40 → floor 40
        self.assertAlmostEqual(self.score().achievement, 40)

    def test_ontime_submission_no_penalty(self):
        a = make_assignment(late_penalty=10)
        submit(a, score=80, submitted_at=PAST - timedelta(hours=1))
        self.assertAlmostEqual(self.score().achievement, 80)

    # ---- 미채점 ----
    def test_ungraded_excluded_from_achievement(self):
        graded = make_assignment(title="g")
        submit(graded, score=90)
        ungraded = make_assignment(title="u")
        submit(ungraded, score=None)
        r = self.score()
        self.assertEqual(r.ungraded_count, 1)
        self.assertEqual(r.graded_count, 1)
        self.assertAlmostEqual(r.achievement, 90)   # ungraded 제외
        self.assertAlmostEqual(r.sincerity, 100)    # 제출은 인정

    def test_all_ungraded_gives_no_final(self):
        a = make_assignment()
        submit(a, score=None)
        r = self.score()
        self.assertIsNone(r.final)
        self.assertEqual(r.ungraded_count, 1)

    # ---- 중요도 가중평균 ----
    def test_tier_weighted_average(self):
        high = make_assignment(title="h", is_required=False, weight_tier="HIGH")
        low = make_assignment(title="l", is_required=False, weight_tier="LOW")
        submit(high, score=80)
        submit(low, score=40)
        # (80*1.5 + 40*0.5) / (1.5+0.5) = 140/2 = 70
        self.assertAlmostEqual(self.score().achievement, 70)

    # ---- 영역 재정규화 ----
    def test_single_area_is_full_weight(self):
        a = make_assignment()
        submit(a, score=72)
        self.assertAlmostEqual(self.score().achievement, 72)

    def test_two_areas_renormalized(self):
        req = make_assignment(title="req", is_required=True)
        opt = make_assignment(title="opt", is_required=False)
        submit(req, score=90)
        submit(opt, score=60)
        # 개인·필수 base .28, 개인·선택 base .42 → norm .4/.6
        # 90*.4 + 60*.6 = 36 + 36 = 72
        self.assertAlmostEqual(self.score().achievement, 72)

    # ---- 팀 과제 ----
    def test_team_assignment_inherits_team_submission(self):
        team = make_assignment(title="team", is_team=True, is_required=True)
        submit(team, student_id=None, team_id=77, score=88)
        with patch("apps.tutor.grading.accounts.get_student_teams",
                   return_value={S: SimpleNamespace(id=77, name="7팀")}):
            r = self.score()
        self.assertAlmostEqual(r.achievement, 88)
        self.assertAlmostEqual(r.sincerity, 100)

    def test_team_assignment_excluded_when_no_team(self):
        make_assignment(title="ind", is_required=True)  # 개인 필수, 미제출 → 10
        make_assignment(title="team", is_team=True, is_required=True)
        with patch("apps.tutor.grading.accounts.get_student_teams", return_value={}):
            r = self.score()
        self.assertAlmostEqual(r.achievement, 10)   # 팀 과제는 성취도에서 빠짐
        self.assertAlmostEqual(r.sincerity, 0)      # 팀 과제는 분모에서도 빠짐 (개인 1개 미제출)
        self.assertEqual(r.total_count, 1)

    # ---- 성실성 ----
    def test_sincerity_ratio(self):
        a1 = make_assignment(title="1")
        a2 = make_assignment(title="2")
        make_assignment(title="3")
        submit(a1, score=50)
        submit(a2, score=None)  # 제출은 함
        r = self.score()
        self.assertAlmostEqual(r.sincerity, round(2 / 3 * 100, 4))

    # ---- 배치 ----
    def test_batch_returns_all_ids(self):
        make_assignment()
        result = grading.compute([S, 999])
        self.assertEqual(set(result), {S, 999})
        self.assertAlmostEqual(result[S].achievement, 10)
        self.assertAlmostEqual(result[999].achievement, 10)
