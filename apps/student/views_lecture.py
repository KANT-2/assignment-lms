import json
from django.shortcuts import render
from apps.core.models import Lecture, Lesson

def student_lecture_list_view(request):
    """강의 및 교안 전체 목록 페이지 (껍데기 화면)"""
    lecture = Lecture.get_singleton()
    lessons = lecture.lessons.all().prefetch_related('videos', 'materials').order_by('-lesson_date') if lecture else []
    
    context = {
        'lecture': lecture,
        'lessons': lessons
    }
    return render(request, 'student/lecture_list.html', context)


def student_lecture_detail_view(request, lesson_id):
    """단일 강의 영상 재생 및 교안 확인 페이지"""
    lecture = Lecture.get_singleton()
    
    # Format lessons for JSON
    lessons_data = []
    if lecture:
        lessons = lecture.lessons.all().prefetch_related('videos', 'materials')
        for idx, lesson in enumerate(lessons):
            materials_data = []
            for mat in lesson.materials.all():
                materials_data.append({
                    'kind': mat.kind,
                    'title': mat.title,
                    'url': mat.file_url if mat.kind == 'FILE' else mat.link_url
                })
            
            lessons_data.append({
                'id': lesson.id,
                'title': lesson.title,
                'date': lesson.lesson_date.strftime('%Y-%m-%d'),
                'videos': [
                    {
                        'title': v.title,
                        'url': v.video_url
                    }
                    for v in lesson.videos.all()
                ],
                'materials': materials_data
            })
    
    context = {
        'lecture': lecture,
        'lessons_json': json.dumps(lessons_data),
        'target_lesson_id': lesson_id
    }
    return render(request, 'student/lecture.html', context)
