# apps/student/views_result.py
# 🧑‍🎓 학생B 전담 — FR-006, FR-014
#
# FR-006 (재제출):
#   - 재제출 허용된 과제 or 튜터가 재제출 요청한 제출물에 대해 다시 제출
#   - 이전 제출 이력 유지, 차수 증가
#   - 저장: apps.core.models.SUBMISSION (새 회차)
#
# FR-014 (평가 결과 확인):
#   - 내 제출물의 EVALUATION 조회 (점수/피드백/통과여부)
#   - 평가 전이면 "평가 대기중" 표시
#   - 템플릿: student/result_view.html
#
# 공통: 본인 제출물만 접근 가능하도록 소유권 체크
