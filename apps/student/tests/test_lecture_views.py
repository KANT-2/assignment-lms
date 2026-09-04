import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Lecture, Lesson, LessonMaterial, LessonVideo


@override_settings(DEV_SKIP_AUTH=True)
class StudentLectureDateGroupingTests(TestCase):
    """같은 날짜에 Lesson 이 여러 개여도 학생 화면은 날짜 단위로 영상을 합쳐 보여준다."""

    databases = {"default"}

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="student-lecture")
        self.client.force_login(self.user)
        self.lecture = Lecture.get_singleton()
        d = date(2026, 9, 4)
        # 같은 날짜, Lesson 2개 — 첫 번째는 영상 없음
        self.l1 = Lesson.objects.create(lecture=self.lecture, title="1부", lesson_date=d)
        self.l2 = Lesson.objects.create(lecture=self.lecture, title="2부", lesson_date=d)
        LessonVideo.objects.create(lesson=self.l2, title="실습", video_url="https://youtu.be/RG-8iv6ORFY", order=0)
        LessonMaterial.objects.create(lesson=self.l2, kind="LINK", title="자료", link_url="https://example.com")

    def _data(self, resp):
        # lessons_json 을 그대로 파싱
        return json.loads(resp.context["lessons_json"])

    def test_detail_merges_same_date_videos(self):
        resp = self.client.get(reverse("student:lecture-detail", args=[self.l1.id]))
        data = self._data(resp)
        self.assertEqual(len(data), 1)  # 날짜 1개로 병합
        entry = data[0]
        self.assertEqual(len(entry["videos"]), 1)
        self.assertEqual(entry["videos"][0]["url"], "https://youtu.be/RG-8iv6ORFY")
        self.assertEqual(len(entry["materials"]), 1)

    def test_detail_normalizes_target_lesson_id_to_group(self):
        # 영상 없는 l1 로 들어와도 target 은 그 날짜 그룹 대표 id
        resp = self.client.get(reverse("student:lecture-detail", args=[self.l1.id]))
        self.assertEqual(resp.context["target_lesson_id"], self.l1.id)  # 대표 = 첫 Lesson
        # l2 로 들어와도 같은 그룹으로
        resp2 = self.client.get(reverse("student:lecture-detail", args=[self.l2.id]))
        self.assertEqual(resp2.context["target_lesson_id"], self.l1.id)

    def test_list_shows_one_row_per_date_with_combined_counts(self):
        resp = self.client.get(reverse("student:lecture-list"))
        lessons = resp.context["lessons"]
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["video_count"], 1)
        self.assertEqual(lessons[0]["material_count"], 1)

    def test_distinct_dates_stay_separate(self):
        Lesson.objects.create(
            lecture=self.lecture, title="다른날", lesson_date=date(2026, 9, 5)
        )
        resp = self.client.get(reverse("student:lecture-detail", args=[self.l1.id]))
        self.assertEqual(len(self._data(resp)), 2)
