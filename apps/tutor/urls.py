from django.urls import path

from . import views_dashboard, views_lecture, views_manage, views_review

app_name = "tutor"

urlpatterns = [
    path("", views_dashboard.dashboard, name="dashboard"),
    path("dashboard/", views_dashboard.dashboard, name="dashboard-alt"),
    path("assignments/", views_manage.assignment_list, name="assignment-list"),
    path("assignments/<int:pk>/edit/", views_manage.assignment_edit, name="assignment-edit"),
    path("assignments/<int:pk>/delete/", views_manage.assignment_delete, name="assignment-delete"),
    path("assignments/<int:pk>/restore/", views_manage.assignment_restore, name="assignment-restore"),
    path("assignments/<int:pk>/submissions/", views_manage.submission_dashboard, name="submission-dashboard"),

    path("lecture/", views_lecture.tutor_lecture_manage_view, name="lecture"),
    path("lecture/api/update/", views_lecture.tutor_lecture_update_api, name="lecture-update-api"),

    # 튜터B — 제출물 검토 / 평가 (FR-011, FR-012, FR-013)
    path("submissions/<int:pk>/review/", views_review.submission_review, name="submission-review"),
    path("submissions/<int:pk>/ai-evaluation/", views_review.ai_evaluation_generate, name="submission-ai-eval"),
]