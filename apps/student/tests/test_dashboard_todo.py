from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Todo


class DashboardTodoTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="todo-student")
        self.client.force_login(self.user)
        for target, val in [
            ("apps.student.views_dashboard.accounts.is_student", True),
            ("apps.student.views_dashboard.accounts.get_user_team", None),
            ("apps.student.views_dashboard.external_student_id", self.user.id),
            ("apps.common.context_processors.accounts.is_tutor", False),
            ("apps.common.context_processors.accounts.is_student", True),
        ]:
            p = patch(target, return_value=val)
            p.start()
            self.addCleanup(p.stop)

        self.today = timezone.localdate()

    def _get(self, **params):
        return self.client.get(reverse("student:dashboard"), params)

    # ---------- add ----------
    def test_add_uses_posted_date(self):
        d = (self.today + timedelta(days=5)).isoformat()
        resp = self.client.post(reverse("student:todo-add"), {"content": "미래 계획", "date": d})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"d={d}", resp["Location"])
        t = Todo.objects.get()
        self.assertEqual(t.due_date.isoformat(), d)
        self.assertEqual(t.student_id, self.user.id)

    def test_add_without_date_defaults_today(self):
        self.client.post(reverse("student:todo-add"), {"content": "그냥"})
        self.assertEqual(Todo.objects.get().due_date, self.today)

    # ---------- date-scoped list ----------
    def test_dashboard_shows_only_selected_days_todos(self):
        Todo.objects.create(student_id=self.user.id, content="오늘꺼", due_date=self.today)
        other = self.today + timedelta(days=2)
        Todo.objects.create(student_id=self.user.id, content="이틀뒤꺼", due_date=other)

        ctx = self._get().context
        self.assertEqual(ctx["todo_date"], self.today)
        self.assertEqual([t.content for t in ctx["todos"]], ["오늘꺼"])

        ctx2 = self._get(y=other.year, m=other.month, d=other.isoformat()).context
        self.assertEqual([t.content for t in ctx2["todos"]], ["이틀뒤꺼"])
        self.assertFalse(ctx2["todo_is_today"])

    def test_todo_done_count(self):
        Todo.objects.create(student_id=self.user.id, content="a", due_date=self.today, is_done=True)
        Todo.objects.create(student_id=self.user.id, content="b", due_date=self.today)
        ctx = self._get().context
        self.assertEqual(ctx["todo_done"], 1)
        self.assertEqual(len(ctx["todos"]), 2)

    # ---------- calendar dot ----------
    def test_calendar_marks_days_with_todos(self):
        Todo.objects.create(student_id=self.user.id, content="x", due_date=self.today)
        weeks = self._get().context["cal"]["weeks"]
        cells = [c for wk in weeks for c in wk if c["date"] == self.today]
        self.assertTrue(cells[0]["has_todo"])
        # 할 일 없는 다른 날은 False
        empty = [c for wk in weeks for c in wk if c["date"] == self.today + timedelta(days=1)]
        self.assertFalse(empty[0]["has_todo"])

    # ---------- toggle / delete keep the day ----------
    def test_toggle_redirects_back_to_todo_day(self):
        d = self.today + timedelta(days=3)
        t = Todo.objects.create(student_id=self.user.id, content="q", due_date=d)
        resp = self.client.post(reverse("student:todo-toggle", args=[t.pk]))
        self.assertIn(f"d={d.isoformat()}", resp["Location"])
        t.refresh_from_db()
        self.assertTrue(t.is_done)

    def test_cannot_touch_other_students_todo(self):
        t = Todo.objects.create(student_id=self.user.id + 999, content="남의것", due_date=self.today)
        self.assertEqual(self.client.post(reverse("student:todo-toggle", args=[t.pk])).status_code, 404)
