from django.urls import path

from . import views_dashboard, views_lecture, views_result, views_submit

app_name = "student"

urlpatterns = [
    path("", views_dashboard.dashboard, name="dashboard"),
    path("", views_dashboard.home, name="home"),
    path("dashboard/", views_dashboard.dashboard, name="dashboard"),
    path("todos/add/", views_dashboard.todo_add, name="todo-add"),
    path("todos/<int:pk>/toggle/", views_dashboard.todo_toggle, name="todo-toggle"),
    path("todos/<int:pk>/delete/", views_dashboard.todo_delete, name="todo-delete"),
    path("lecture/", views_lecture.student_lecture_view, name="lecture"),
    path("assignments/", views_submit.assignment_list, name="assignment-list"),
    path("assignments/<int:assignment_id>/submit/", views_submit.assignment_submit, name="assignment-submit"),
    path("assignments/<int:assignment_id>/preview/", views_submit.assignment_preview, name="assignment-preview"),
    path("results/", views_result.result_list, name="result-list"),
    path("submissions/<int:submission_id>/resubmit/", views_result.resubmit, name="submission-resubmit"),
    path("submissions/<int:submission_id>/result/", views_result.result, name="submission-result"),
    path("lecture/", views_lecture.student_lecture_view, name="lecture"),
]
