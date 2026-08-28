"""
apps/student/urls.py
학생팀 — student 앱 URL 라우팅 (config/urls.py 에서 include).

담당 매핑 (뷰는 아직 미구현 — 스텁):
  ""|dashboard/                  -> 대시보드 (dashboard.html)
  assignments/                   -> 학생A: 과제 목록      (FR-003)  views_submit
  assignments/<id>/submit/       -> 학생A: 과제 제출      (FR-004)  views_submit
  assignments/<id>/preview/      -> 학생A: 제출 미리보기  (FR-005)  views_submit
  submissions/<id>/resubmit/     -> 학생B: 재제출         (FR-006)  views_result
  submissions/<id>/result/       -> 학생B: 평가 결과      (FR-014)  views_result
"""
from django.urls import path

from . import views_dashboard, views_result, views_submit

app_name = "student"

urlpatterns: list[path] = [
    # 학생 메인 대시보드 (PRD 7장) — 학생 A/B 담당과 별개

    path("", views_dashboard.dashboard, name="dashboard"),
    path("", views_dashboard.home, name="home"),
    path("dashboard/", views_dashboard.dashboard, name="dashboard"),
    path("todos/add/", views_dashboard.todo_add, name="todo-add"),
    path("todos/<int:pk>/toggle/", views_dashboard.todo_toggle, name="todo-toggle"),
    path("todos/<int:pk>/delete/", views_dashboard.todo_delete, name="todo-delete"),
    path("assignments/", views_submit.assignment_list, name="assignment-list"),
    path("assignments/<int:assignment_id>/submit/", views_submit.assignment_submit, name="assignment-submit"),
    path("assignments/<int:assignment_id>/preview/", views_submit.assignment_preview, name="assignment-preview"),
    path("submissions/<int:submission_id>/resubmit/", views_result.resubmit, name="submission-resubmit"),
    path("submissions/<int:submission_id>/result/", views_result.result, name="submission-result"),
]
