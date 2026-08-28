import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from apps.core.models import Lecture, Lesson, LessonMaterial

def tutor_lecture_manage_view(request):
    lecture, created = Lecture.objects.get_or_create(title="AX 실무 프로젝트 집중 과정")
    
    lessons_data = []
    lessons = lecture.lessons.all().prefetch_related('materials')
    for idx, lesson in enumerate(lessons):
        materials_data = []
        for mat in lesson.materials.all():
            materials_data.append({
                'kind': mat.kind,
                'title': mat.title,
                'size': '0 MB',
                'url': mat.file_url if mat.kind == 'FILE' else mat.link_url
            })
        
        lessons_data.append({
            'id': lesson.id,
            'order': idx + 1,
            'title': lesson.title,
            'date': lesson.lesson_date.strftime('%Y-%m-%d'),
            'blogUrl': lesson.blog_link,
            'videoUrl': lesson.video_url,
            'materials': materials_data
        })
    
    context = {
        'lecture': lecture,
        'lessons_json': json.dumps(lessons_data)
    }
    return render(request, 'tutor/lecture_manage.html', context)

@csrf_exempt
def tutor_lecture_update_api(request):
    if request.method == 'POST':
        lecture = Lecture.objects.first()
        data = json.loads(request.body)
        lessons_list = data.get('lessons', [])
        
        # Simple sync: update existing, create new, delete missing
        existing_lesson_ids = set(lecture.lessons.values_list('id', flat=True))
        incoming_ids = set()
        
        for idx, l_data in enumerate(lessons_list):
            l_id = l_data.get('id')
            if l_id and l_id in existing_lesson_ids:
                # Update
                lesson = Lesson.objects.get(id=l_id)
                lesson.title = l_data.get('title', '')
                lesson.lesson_date = l_data.get('date')
                lesson.blog_link = l_data.get('blogUrl')
                lesson.video_url = l_data.get('videoUrl')
                lesson.save()
                incoming_ids.add(l_id)
            else:
                # Create (or recreate if id was fake)
                lesson = Lesson.objects.create(
                    lecture=lecture,
                    title=l_data.get('title', ''),
                    lesson_date=l_data.get('date'),
                    blog_link=l_data.get('blogUrl'),
                    video_url=l_data.get('videoUrl')
                )
                incoming_ids.add(lesson.id)
            
            # Sync materials (just delete and recreate for simplicity)
            lesson.materials.all().delete()
            for mat in l_data.get('materials', []):
                LessonMaterial.objects.create(
                    lesson=lesson,
                    kind=mat.get('kind', 'FILE'),
                    title=mat.get('title', ''),
                    file_url=mat.get('url') if mat.get('kind') == 'FILE' else None,
                    link_url=mat.get('url') if mat.get('kind') == 'LINK' else None
                )
                
        # Delete lessons not in incoming
        for l_id in existing_lesson_ids - incoming_ids:
            Lesson.objects.filter(id=l_id).delete()
            
        # Return updated lessons so frontend gets real DB IDs
        updated_lessons = []
        for idx, lesson in enumerate(lecture.lessons.all().prefetch_related('materials')):
            updated_lessons.append({
                'id': lesson.id,
                'order': idx + 1,
                'title': lesson.title,
                'date': lesson.lesson_date.strftime('%Y-%m-%d'),
                'blogUrl': lesson.blog_link,
                'videoUrl': lesson.video_url,
                'materials': [
                    {'kind': mat.kind, 'title': mat.title, 'size': '0 MB', 'url': mat.file_url if mat.kind == 'FILE' else mat.link_url}
                    for mat in lesson.materials.all()
                ]
            })
            
        return JsonResponse({'status': 'success', 'lessons': updated_lessons})
    return JsonResponse({'status': 'error'}, status=400)
