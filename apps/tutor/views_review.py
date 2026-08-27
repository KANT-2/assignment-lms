# apps/tutor/views_review.py
# 👨‍🏫 튜터B 전담 — FR-011, FR-012, FR-013
#
# FR-011 (평가 입력):
#   - 제출물에 점수/피드백/통과여부 입력
#   - 저장: apps.core.models.EVALUATION (SUBMISSION 1:1)
#   - 템플릿: tutor/review_panel.html
#
# FR-012 (평가 수정):
#   - 기존 평가 내용 수정, 수정 이력 표시(선택)
#
# FR-013 (평가 목록/필터):
#   - 평가 대기 / 평가 완료 목록, 과제·학생·상태별 필터
#
# 공통: 튜터 권한 체크
