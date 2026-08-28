from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Assignment, Evaluation, Submission

STUDENTS = [SimpleNamespace(id=i, name=f"학생{i}", email=f"s{i}@x.io", role="student") for i in (1, 2, 3)]


class TutorStudentMgmtTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tutor-stu")
        self.client.force_login(self.user)
        for name, val in [
            ("apps.tutor.views_student.accounts.is_tutor", True),
            ("apps.tutor.views_student.accounts.get_students", STUDENTS),
        ]:
            p = patch(name, return_value=val)
            p.start()
            self.addCleanup(p.stop)
        p = patch("apps.tutor.views_student.accounts.get_user",
                  side_effect=lambda sid: next((s for s in STUDENTS if s.id == sid), None))
        p.start()
        self.addCleanup(p.stop)

    def _a(self, **kw):
        d = dict(title="과제", due_at=timezone.now() + timedelta(days=1),
                 is_team=False, is_required=True, allow_late=True, created_by=self.user.id)
        d.update(kw)
        return Assignment.objects.create(**d)

    # ---------- list ----------
    def test_list_requires_tutor(self):
        with patch("apps.tutor.views_student.accounts.is_tutor", return_value=False):
            self.assertEqual(self.client.get(reverse("tutor:student-list")).status_code, 403)

    def test_required_rate_personal_only(self):
        r1 = self._a(title="필수1")
        r2 = self._a(title="필수2")
        self._a(title="팀과제", is_team=True)          # 분모에서 제외돼야 함
        self._a(title="선택1", is_required=False)
        Submission.objects.create(assignment=r1, student_id=1)   # 학생1: 2개 중 1개

        rows = {r["id"]: r for r in self.client.get(reverse("tutor:student-list")).context["rows"]}
        self.assertEqual(rows[1]["req_total"], 2)
        self.assertEqual(rows[1]["req_done"], 1)
        self.assertEqual(rows[1]["req_rate"], 50)
        self.assertEqual(rows[1]["opt_total"], 1)
        self.assertEqual(rows[2]["req_done"], 0)

    def test_students_with_missing_counts_overdue_unsubmitted(self):
        self._a(title="지난 필수", due_at=timezone.now() - timedelta(days=1))
        Submission.objects.create(assignment=Assignment.objects.get(title="지난 필수"), student_id=1)
        ctx = self.client.get(reverse("tutor:student-list")).context
        # 학생2, 학생3 은 미제출
        self.assertEqual(ctx["students_with_missing"], 2)

    def test_sort_by_name(self):
        self._a()
        ctx = self.client.get(reverse("tutor:student-list"), {"sort": "name"}).context
        self.assertEqual([r["name"] for r in ctx["rows"]], ["학생1", "학생2", "학생3"])

    # ---------- detail ----------
    def test_detail_timeline_statuses(self):
        done = self._a(title="제출완료", due_at=timezone.now() + timedelta(days=2))
        late = self._a(title="지각", due_at=timezone.now() - timedelta(days=2))
        missing = self._a(title="미제출", due_at=timezone.now() - timedelta(days=1))
        upcoming = self._a(title="마감전", due_at=timezone.now() + timedelta(days=3))
        Submission.objects.create(assignment=done, student_id=1)
        s_late = Submission.objects.create(assignment=late, student_id=1)
        Submission.objects.filter(pk=s_late.pk).update(submitted_at=timezone.now())

        ctx = self.client.get(reverse("tutor:student-detail", args=[1])).context
        status = {t["assignment"].title: t["status"] for t in ctx["timeline"]}
        self.assertEqual(status["제출완료"], "제출완료")
        self.assertEqual(status["지각"], "지각 제출")
        self.assertEqual(status["미제출"], "미제출")
        self.assertEqual(status["마감전"], "마감 전")

    def test_detail_score_shows_only_graded(self):
        a = self._a(due_at=timezone.now() - timedelta(days=1))
        sub = Submission.objects.create(assignment=a, student_id=1)
        Evaluation.objects.create(submission=sub, score=88, feedback="ok")
        ctx = self.client.get(reverse("tutor:student-detail", args=[1])).context
        self.assertEqual(ctx["timeline"][0]["score"], 88)

    def test_detail_unknown_student_403(self):
        self.assertEqual(self.client.get(reverse("tutor:student-detail", args=[999])).status_code, 403)
