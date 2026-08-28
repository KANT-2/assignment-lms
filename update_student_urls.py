import sys

with open(r'c:\dev\assignment-lms\apps\student\urls.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('from . import views_dashboard', 'from . import views_dashboard, views_lecture')
text = text.replace(']', '    path("lecture/", views_lecture.student_lecture_view, name="lecture"),\n]')

with open(r'c:\dev\assignment-lms\apps\student\urls.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("Updated student urls")
