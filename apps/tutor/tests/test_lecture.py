import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import Lecture, Lesson


class LectureSingletonTests(TestCase):
    databases = {"default"}

    def test_get_singleton_creates_when_empty(self):
        self.assertEqual(Lecture.objects.count(), 0)
        lecture = Lecture.get_singleton()
        self.assertEqual(Lecture.objects.count(), 1)
        self.assertEqual(Lecture.get_singleton().pk, lecture.pk)

    def test_get_singleton_is_lowest_id_regardless_of_title(self):
        first = Lecture.objects.create(title="원래 강의")
        Lecture.objects.create(title=Lecture.DEFAULT_TITLE)  # 유령 후보
        self.assertEqual(Lecture.get_singleton().pk, first.pk)


class TutorLectureViewTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tutor-lecture")
        self.client.force_login(self.user)
        p = patch("apps.tutor.views_manage.accounts.is_tutor", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def _post(self, payload, client=None):
        return (client or self.client).post(
            reverse("tutor:lecture-update-api"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_manage_view_requires_tutor(self):
        with patch("apps.tutor.views_manage.accounts.is_tutor", return_value=False):
            response = self.client.get(reverse("tutor:lecture"))
        self.assertEqual(response.status_code, 403)

    def test_update_creates_and_persists_across_reload(self):
        rev = self.client.get(reverse("tutor:lecture")).context["revision"]
        response = self._post({
            "base_revision": rev,
            "lessons": [
                {"id": 1724800000000, "title": "1회차", "date": "2026-03-02",
                 "blogUrl": None, "videoUrl": None, "materials": []},
            ],
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["lessons"]), 1)
        self.assertIsInstance(body["lessons"][0]["id"], int)
        self.assertEqual(Lesson.objects.count(), 1)

        # 재방문 시 그대로 보인다
        ctx = self.client.get(reverse("tutor:lecture")).context
        reloaded = json.loads(ctx["lessons_json"])
        self.assertEqual(reloaded[0]["title"], "1회차")

    def test_stale_revision_is_rejected_without_data_loss(self):
        rev = self.client.get(reverse("tutor:lecture")).context["revision"]
        self._post({"base_revision": rev, "lessons": [
            {"id": 1, "title": "먼저", "date": "2026-03-02", "materials": []}]})

        # 낡은 revision 으로 전부 지우려는 두 번째 저장
        response = self._post({"base_revision": rev, "lessons": []})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "stale")
        self.assertEqual(Lesson.objects.count(), 1)  # 안 지워짐

    def test_update_api_rejects_get(self):
        self.assertEqual(self.client.get(reverse("tutor:lecture-update-api")).status_code, 405)

    def test_update_api_enforces_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            reverse("tutor:lecture-update-api"),
            data=json.dumps({"lessons": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
