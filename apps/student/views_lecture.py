import json
from collections import OrderedDict

from django.shortcuts import render

from apps.core.models import Lecture


def _lessons_by_date(lecture):
    """같은 날짜의 Lesson 들을 하나로 묶는다 (일자별 강의 모델).

    튜터는 한 날짜에 Lesson 을 여러 개 만들 수 있지만(1부/2부 등), 학생 화면은
    "그 날의 강의" 하나로 본다 → 영상·자료를 날짜 단위로 합친다.
    반환: [{id, lesson_ids, title, date(date), videos:[...], materials:[...]}, ...] · 날짜 오름차순
    """
    groups: OrderedDict = OrderedDict()
    if not lecture:
        return []
    lessons = (
        lecture.lessons.all()
        .prefetch_related("videos", "materials")
        .order_by("lesson_date", "id")
    )
    for lesson in lessons:
        group = groups.get(lesson.lesson_date)
        if group is None:
            group = {
                "id": lesson.id,          # 대표 id (그 날짜 첫 Lesson) — URL 정규화용
                "lesson_ids": [],
                "title": lesson.title,    # 여러 개면 첫 Lesson 제목
                "date": lesson.lesson_date,
                "videos": [],
                "materials": [],
            }
            groups[lesson.lesson_date] = group
        group["lesson_ids"].append(lesson.id)
        for video in lesson.videos.all():
            group["videos"].append({"title": video.title, "url": video.video_url})
        for mat in lesson.materials.all():
            group["materials"].append({
                "kind": mat.kind,
                "title": mat.title,
                "url": mat.file_url if mat.kind == "FILE" else mat.link_url,
            })
    return list(groups.values())


def student_lecture_list_view(request):
    """강의 및 교안 전체 목록 페이지 (날짜 단위)."""
    lecture = Lecture.get_singleton()
    groups = _lessons_by_date(lecture)
    lessons = [
        {
            "id": g["id"],
            "title": g["title"],
            "lesson_date": g["date"],
            "video_count": len(g["videos"]),
            "material_count": len(g["materials"]),
        }
        for g in reversed(groups)  # 최신 날짜 먼저
    ]
    return render(request, "student/lecture_list.html", {"lecture": lecture, "lessons": lessons})


def student_lecture_detail_view(request, lesson_id):
    """단일 강의 영상 재생 및 교안 확인 페이지 (날짜 단위)."""
    lecture = Lecture.get_singleton()
    groups = _lessons_by_date(lecture)

    # 요청한 lesson_id 가 속한 날짜 그룹의 대표 id 로 정규화 (프론트가 id 로 그룹을 찾음)
    target_id = lesson_id
    for group in groups:
        if lesson_id in group["lesson_ids"]:
            target_id = group["id"]
            break

    lessons_data = [
        {
            "id": g["id"],
            "title": g["title"],
            "date": g["date"].strftime("%Y-%m-%d"),
            "videos": g["videos"],
            "materials": g["materials"],
        }
        for g in groups
    ]

    context = {
        "lecture": lecture,
        "lessons_json": json.dumps(lessons_data),
        "target_lesson_id": target_id,
    }
    return render(request, "student/lecture.html", context)
