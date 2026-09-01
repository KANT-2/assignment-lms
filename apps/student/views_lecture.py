import json
from django.shortcuts import render
from apps.core.models import Lecture, Lesson

def student_lecture_view(request):
    # Fetch the single course (BR-001) — 튜터 화면과 같은 헬퍼로 항상 동일 행을 본다.
    lecture = Lecture.get_singleton()
    
    # Format lessons for JSON
    lessons_data = []
    if lecture:
        lessons = lecture.lessons.all().prefetch_related('materials')
        for idx, lesson in enumerate(lessons):
            materials_data = []
            for mat in lesson.materials.all():
                materials_data.append({
                    'kind': mat.kind,
                    'title': mat.title,
                    'size': '0 MB', # Dummy size for now, as DB lacks file size in LessonMaterial
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
        'lessons_json': json.dumps(lessons_data)
    }
    return render(request, 'student/lecture.html', context)
