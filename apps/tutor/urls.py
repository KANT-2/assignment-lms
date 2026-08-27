"""
apps/tutor/urls.py
튜터팀 — tutor 앱 URL 라우팅 (config/urls.py 에서 include).

담당 매핑 (뷰는 아직 미구현 — 스텁):
  assignments/                        -> 튜터A: 과제 목록/생성       (FR-001)      views_manage
  assignments/<id>/edit/              -> 튜터A: 수정/삭제/공개설정   (FR-002)      views_manage
  assignments/<id>/submissions/       -> 튜터A: 제출 현황 대시보드   (FR-007)      views_manage
  submissions/<id>/                   -> 튜터A: 제출물 상세          (FR-008)      views_manage
  submissions/<id>/request-resubmit/  -> 튜터A: 재제출 요청          (FR-010)      views_manage
  submissions/<id>/review/            -> 튜터B: 평가 입력/수정       (FR-011,012)  views_review
  reviews/                            -> 튜터B: 평가 목록/필터       (FR-013)      views_review
"""
from django.urls import path

app_name = "tutor"

urlpatterns: list[path] = [
    # 예)
    # path("assignments/", views_manage.AssignmentManageView.as_view(), name="assignment-manage"),
]
