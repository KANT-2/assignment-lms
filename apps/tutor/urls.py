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