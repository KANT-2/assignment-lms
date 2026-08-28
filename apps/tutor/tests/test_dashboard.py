from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, Evaluation, Lesson, Lecture, Submission


class TutorDashboardTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tutor-test")
        self.client.force_login(self.user)
        patcher = patch(
            "apps.tutor.views_dashboard.accounts.is_tutor", return_value=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self._mock_roster([SimpleNamespace(id=i, name=f"학생{i}", email="") for i in range(1, 6)],
                          [SimpleNamespace(id=1, name="1팀"), SimpleNamespace(id=2, name="2팀")])

    def _mock_roster(self, students, teams):
        for name, val in [("get_students", students), ("get_teams", teams)]:
            p = patch(f"apps.tutor.views_dashboard.accounts.{name}", return_value=val)
            p.start()
            self.addCleanup(p.stop)
        p = patch("apps.tutor.views_dashboard.accounts.get_users",
                  side_effect=lambda ids: {i: SimpleNamespace(id=i, name=f"학생{i}", email="") for i in ids})
        p.start()
        self.addCleanup(p.stop)

    def _assignment(self, **kw):
        defaults = dict(
            title="과제", due_at=timezone.now() + timedelta(days=1),
            is_team=False, allow_late=True, created_by=self.user.id,
        )
        defaults.update(kw)
        return Assignment.objects.create(**defaults)

    def test_dashboard_renders_for_tutor(self):
        self._assignment(title="진행 중 과제")
        response = self.client.get(reverse("tutor:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "진행 중 과제")
        self.assertContains(response, "튜터 · 대시보드")

    def test_non_tutor_is_forbidden(self):
        with patch("apps.tutor.views_dashboard.accounts.is_tutor", return_value=False):
            response = self.client.get(reverse("tutor:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_feedback_queue_lists_past_due_unevaluated(self):
        past = self._assignment(title="마감된 과제", due_at=timezone.now() - timedelta(days=1))
        graded_a = self._assignment(title="평가된 과제", due_at=timezone.now() - timedelta(days=2))
        Submission.objects.create(assignment=past, student_id=1)
        graded = Submission.objects.create(assignment=graded_a, student_id=2)
        Evaluation.objects.create(submission=graded, score=90, feedback="ok")

        response = self.client.get(reverse("tutor:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "마감된 과제")
        self.assertEqual(response.context["feedback_pending_count"], 1)

    def test_not_submitted_counts_against_roster(self):
        self._assignment(title="개인 과제")  # 5명 중 0명 제출
        response = self.client.get(reverse("tutor:dashboard"))
        rows = response.context["not_submitted"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["missing"], 5)

    def test_lesson_needs_attention_when_past_and_empty(self):
        lecture = Lecture.objects.create(title="AX")
        Lesson.objects.create(lecture=lecture, title="지난 빈 수업",
                              lesson_date=timezone.localdate() - timedelta(days=3))
        response = self.client.get(reverse("tutor:dashboard"))
        self.assertEqual(response.context["lesson_prep_needed"], 1)

    def test_renders_team_assignment_and_prepared_lesson(self):
        team_a = self._assignment(title="팀 과제", is_team=True,
                                  due_at=timezone.now() + timedelta(hours=12))
        Submission.objects.create(assignment=team_a, team_id=1)
        lecture = Lecture.objects.create(title="AX")
        Lesson.objects.create(lecture=lecture, title="완비된 수업",
                              lesson_date=timezone.localdate() - timedelta(days=1),
                              video_url="https://youtu.be/x")

        response = self.client.get(reverse("tutor:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "팀 과제")
        self.assertContains(response, "완비된 수업")
        self.assertContains(response, "영상 ✓")
        # 마감 임박(12시간 뒤) 집계
        self.assertEqual(response.context["summary"]["imminent"], 1)
