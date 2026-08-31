"""
apps/tutor/grading — 전체 시나리오 통합 검증.

한 기수(과제 6개 + 마감전 1 + 삭제 1)에 성격이 다른 학생 7명을 놓고,
손으로 계산한 값과 grading.compute 결과를 대조한다.

정책 기본값: 성취도 0.7 / 성실성 0.3, 개인:팀 = 0.7:0.3, 선택:필수 = 0.6:0.4,
             필수 floor 40 / 선택 floor 20 / 필수 미제출 10, 중요도 상1.5 중1.0 하0.5.
영역 기본 가중치: 개인·필수 .28 / 개인·선택 .42 / 팀·필수 .12 / 팀·선택 .18
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Assignment, Submission
from apps.tutor import grading

NOW = timezone.now()
PAST = NOW - timedelta(days=2)
BEFORE = PAST - timedelta(hours=3)   # 정시 제출 시각
FUTURE = NOW + timedelta(days=3)

S1, S2, S3, S4, S5, S6, S7 = 101, 102, 103, 104, 105, 106, 107
T1, T2 = 1, 2


def A(key, *, team, required, tier, late_penalty=0, due=PAST, deleted=False):
    a = Assignment.objects.create(
        title=key, due_at=due, is_team=team, is_required=required,
        weight_tier=tier, late_penalty=late_penalty, created_by=1,
    )
    if deleted:
        Assignment.all_objects.filter(pk=a.pk).update(deleted_at=NOW)
    return a


def sub(assignment, *, student=None, team=None, score=None, late=False):
    s = Submission.objects.create(
        assignment=assignment, student_id=student, team_id=team, final_score=score,
    )
    Submission.objects.filter(pk=s.pk).update(submitted_at=NOW if late else BEFORE)
    return s


class FullCohortScenario(TestCase):
    databases = {"default"}

    def setUp(self):
        self.ir1 = A("IR1", team=False, required=True, tier="MID")
        self.ir2 = A("IR2", team=False, required=True, tier="HIGH", late_penalty=20)
        self.io1 = A("IO1", team=False, required=False, tier="MID")
        self.io2 = A("IO2", team=False, required=False, tier="LOW")
        self.tr1 = A("TR1", team=True, required=True, tier="MID")
        self.to1 = A("TO1", team=True, required=False, tier="HIGH")
        A("FUTURE", team=False, required=True, tier="MID", due=FUTURE)      # 무시돼야 함
        A("DELETED", team=False, required=True, tier="MID", deleted=True)   # 무시돼야 함

        # 팀 제출물 (팀당 1행)
        sub(self.tr1, team=T1, score=85)
        sub(self.to1, team=T1, score=60)
        sub(self.tr1, team=T2, score=40)
        # TO1 은 T2 미제출

        # S1 — 모범
        sub(self.ir1, student=S1, score=90)
        sub(self.ir2, student=S1, score=100)
        sub(self.io1, student=S1, score=80)
        sub(self.io2, student=S1, score=70)
        # S2 — 엉망 (미제출·지각·미채점 섞임)
        sub(self.ir2, student=S2, score=90, late=True)   # 90-20=70
        sub(self.io1, student=S2, score=None)            # 미채점 → 제외
        # IR1, IO2 미제출
        # S3 — 필수만
        sub(self.ir1, student=S3, score=75)
        sub(self.ir2, student=S3, score=50)              # floor 40 걸림? 50 → 그대로
        # S4 — 팀 없음
        sub(self.ir1, student=S4, score=100)
        sub(self.io1, student=S4, score=90)
        sub(self.io2, student=S4, score=30)
        # IR2 미제출
        # S5 — 개인 전부 미제출, 팀(T2)만 상속
        # S6 — 완전 무활동, 팀 없음
        # S7 — 개인 전부 제출했으나 전부 미채점, 팀 없음
        for a in (self.ir1, self.ir2, self.io1, self.io2):
            sub(a, student=S7, score=None)

        self.teams = {S1: SimpleNamespace(id=T1), S2: SimpleNamespace(id=T1),
                      S3: SimpleNamespace(id=T2), S5: SimpleNamespace(id=T2)}

    def results(self):
        with patch("apps.tutor.grading.accounts.get_student_teams", return_value=self.teams):
            return grading.compute([S1, S2, S3, S4, S5, S6, S7], now=NOW)

    def test_s1_model_student(self):
        r = self.results()[S1]
        # 개인필수 (90*1 + 100*1.5)/2.5 = 96 ; 개인선택 (80*1 + 70*.5)/1.5 = 76.6667
        # 팀필수 85 ; 팀선택 60 ; 전 영역 존재 → 재정규화 없음
        # 성취도 96*.28 + 76.6667*.42 + 85*.12 + 60*.18 = 80.08
        self.assertAlmostEqual(r.achievement, 80.08, places=2)
        self.assertEqual(r.sincerity, 100)
        self.assertEqual(r.final, 86.1)          # 80.08*.7 + 100*.3 = 86.056
        self.assertEqual(r.ungraded_count, 0)

    def test_s2_messy(self):
        r = self.results()[S2]
        # 개인필수 (10*1 + 70*1.5)/2.5 = 46 ; 개인선택 (0*.5)/.5 = 0 (IO1 미채점 제외)
        # 팀필수 85 ; 팀선택 60
        # 성취도 46*.28 + 0 + 85*.12 + 60*.18 = 33.88
        self.assertAlmostEqual(r.achievement, 33.88, places=2)
        # 제출: IR2, IO1, TR1, TO1 = 4 / 6
        self.assertAlmostEqual(r.sincerity, 66.6667, places=3)
        self.assertEqual(r.final, 43.7)          # 33.88*.7 + 66.667*.3 = 43.716
        self.assertEqual(r.ungraded_count, 1)

    def test_s3_required_only(self):
        r = self.results()[S3]
        # 개인필수 (75*1 + 50*1.5)/2.5 = 60 ; 개인선택 (0+0)/1.5 = 0
        # 팀필수 40 (floor) ; 팀선택 0 (T2 미제출)
        # 성취도 60*.28 + 0 + 40*.12 + 0 = 21.6
        self.assertAlmostEqual(r.achievement, 21.6, places=2)
        self.assertEqual(r.sincerity, 50)       # IR1, IR2, TR1 = 3/6
        self.assertEqual(r.final, 30.1)          # 21.6*.7 + 50*.3 = 30.12

    def test_s4_no_team_renormalizes(self):
        r = self.results()[S4]
        # 개인필수 (100*1 + 10*1.5)/2.5 = 46 ; 개인선택 (90*1 + 30*.5)/1.5 = 70
        # 팀 영역 없음 → 재정규화: .28/.42 → .4/.6
        # 성취도 46*.4 + 70*.6 = 60.4
        self.assertAlmostEqual(r.achievement, 60.4, places=2)
        self.assertEqual(r.sincerity, 75)       # IR1, IO1, IO2 = 3/4 (팀 과제는 분모 제외)
        self.assertEqual(r.final, 64.8)          # 60.4*.7 + 75*.3 = 64.78
        self.assertEqual(r.total_count, 4)

    def test_s5_inherits_team_only(self):
        r = self.results()[S5]
        # 개인필수 (10*1 + 10*1.5)/2.5 = 10 ; 개인선택 0
        # 팀필수 40 (T2 상속) ; 팀선택 0 (T2 미제출)
        # 성취도 10*.28 + 0 + 40*.12 + 0 = 7.6
        self.assertAlmostEqual(r.achievement, 7.6, places=2)
        self.assertAlmostEqual(r.sincerity, 16.6667, places=3)   # TR1만 = 1/6
        self.assertEqual(r.final, 10.3)          # 7.6*.7 + 16.667*.3 = 10.32

    def test_s6_totally_inactive(self):
        r = self.results()[S6]
        # 개인필수 (10*1 + 10*1.5)/2.5 = 10 ; 개인선택 0 ; 팀 없음 → 재정규화 .4/.6
        # 성취도 10*.4 + 0*.6 = 4.0
        self.assertAlmostEqual(r.achievement, 4.0, places=2)
        self.assertEqual(r.sincerity, 0)
        self.assertEqual(r.final, 2.8)           # 4.0*.7 + 0
        self.assertEqual(r.total_count, 4)

    def test_s7_all_ungraded_no_final(self):
        r = self.results()[S7]
        self.assertIsNone(r.achievement)
        self.assertIsNone(r.final)
        self.assertEqual(r.ungraded_count, 4)
        self.assertEqual(r.sincerity, 100)      # 제출은 다 함

    def test_future_and_deleted_ignored(self):
        r = self.results()[S6]
        # 대상 과제 = 개인 4개 (IR1,IR2,IO1,IO2). FUTURE/DELETED 빠짐, 팀 없어서 팀 2개 빠짐
        self.assertEqual(r.total_count, 4)


class PolicyAndEdgeTests(TestCase):
    databases = {"default"}

    def test_policy_change_is_reflected(self):
        a = Assignment.objects.create(
            title="x", due_at=PAST, is_team=False, is_required=True,
            weight_tier="MID", created_by=1,
        )
        Submission.objects.create(assignment=a, student_id=1, final_score=100)
        base = grading.compute([1], now=NOW)[1].final     # 100*.7 + 100*.3 = 100
        self.assertEqual(base, 100.0)

        from apps.tutor.models import GradingPolicy
        p = GradingPolicy.get_solo()
        p.achievement_weight = 0.5
        p.sincerity_weight = 0.5
        p.save()
        again = grading.compute([1], now=NOW)[1].final
        self.assertEqual(again, 100.0)  # 여전히 100 (둘 다 100)

        # 미제출 학생으로 비중 변화 확인
        Submission.objects.filter(assignment=a).delete()
        # 성취도 10, 성실성 0 → 0.5/0.5 → 5.0  (기본 0.7/0.3 이면 7.0)
        self.assertEqual(grading.compute([1], now=NOW)[1].final, 5.0)

    def test_empty_input(self):
        self.assertEqual(grading.compute([]), {})

    def test_no_assignments_at_all(self):
        self.assertIsNone(grading.compute([1], now=NOW)[1].final)

    def test_get_student_teams_failure_falls_back_to_no_team(self):
        a = Assignment.objects.create(
            title="t", due_at=PAST, is_team=True, is_required=True,
            weight_tier="MID", created_by=1,
        )
        Submission.objects.create(assignment=a, team_id=9, final_score=100)
        with patch("apps.tutor.grading.accounts.get_student_teams", side_effect=RuntimeError):
            r = grading.compute([1], now=NOW)[1]
        # 팀 조회 실패 → 팀 없음 취급 → 팀 과제뿐이라 산출 불가
        self.assertIsNone(r.final)
        self.assertEqual(r.total_count, 0)
