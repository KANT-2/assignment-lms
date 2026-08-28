import sys

with open(r'c:\dev\assignment-lms\apps\tutor\urls.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('from . import views_manage', 'from . import views_manage, views_lecture')
text = text.replace(']', '    path("lecture/", views_lecture.tutor_lecture_manage_view, name="lecture"),\n    path("lecture/api/update/", views_lecture.tutor_lecture_update_api, name="lecture-update-api"),\n]')

with open(r'c:\dev\assignment-lms\apps\tutor\urls.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("Updated tutor urls")
