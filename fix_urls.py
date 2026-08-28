import sys

def fix_urls(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Revert the broken list[path    path(...) replacement
    # We will just rewrite the whole file cleanly.

import re

# Rewrite student urls.py
student_urls = """
from django.urls import path
from . import views_dashboard, views_lecture

app_name = "student"

urlpatterns = [
    path("", views_dashboard.dashboard, name="dashboard"),
    path("todos/add/", views_dashboard.todo_add, name="todo-add"),
    path("todos/<int:pk>/toggle/", views_dashboard.todo_toggle, name="todo-toggle"),
    path("todos/<int:pk>/delete/", views_dashboard.todo_delete, name="todo-delete"),
    path("lecture/", views_lecture.student_lecture_view, name="lecture"),
]
"""
with open(r'c:\dev\assignment-lms\apps\student\urls.py', 'w', encoding='utf-8') as f:
    f.write(student_urls.strip())

# Rewrite tutor urls.py
tutor_urls = """
from django.urls import path
from . import views_manage, views_lecture

app_name = "tutor"

urlpatterns = [
    path("assignments/", views_manage.assignment_list, name="assignment-list"),
    path("assignments/<int:pk>/edit/", views_manage.assignment_edit, name="assignment-edit"),
    path("assignments/<int:pk>/delete/", views_manage.assignment_delete, name="assignment-delete"),
    path("assignments/<int:pk>/restore/", views_manage.assignment_restore, name="assignment-restore"),
    path("assignments/<int:pk>/submissions/", views_manage.submission_dashboard, name="submission-dashboard"),
    
    path("lecture/", views_lecture.tutor_lecture_manage_view, name="lecture"),
    path("lecture/api/update/", views_lecture.tutor_lecture_update_api, name="lecture-update-api"),
]
"""
with open(r'c:\dev\assignment-lms\apps\tutor\urls.py', 'w', encoding='utf-8') as f:
    f.write(tutor_urls.strip())

print("URLs fixed!")
