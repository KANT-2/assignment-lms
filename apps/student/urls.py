from django.urls import path
from . import views_dashboard, views_lecture, views_submit

app_name = "student"

urlpatterns = [
    path("", views_dashboard.dashboard, name="dashboard"),
    path("todos/add/", views_dashboard.todo_add, name="todo-add"),
    path("todos/<int:pk>/toggle/", views_dashboard.todo_toggle, name="todo-toggle"),
    path("todos/<int:pk>/delete/", views_dashboard.todo_delete, name="todo-delete"),
    path("lecture/", views_lecture.student_lecture_view, name="lecture"),
    path("assignments/", views_submit.assignment_list, name="assignment-list"),
    path("assignments/<int:pk>/submit/", views_submit.submission_form, name="submission-form"),
]