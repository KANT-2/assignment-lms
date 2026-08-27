# apps/student/views_submit.py
# 🧑‍🎓 학생A 전담 — FR-003, FR-004, FR-005
#
# FR-003 (과제 목록):
#   - 로그인한 학생이 볼 수 있는 과제 목록 (공개 상태 + 소속 강의 기준)
#   - 각 과제의 제출 상태 표시 (미제출 / 제출완료 / 평가완료), 마감일
#   - 템플릿: student/assignment_list.html
#
# FR-004 (과제 제출):
#   - 과제 상세 + 제출 폼 (본문 + 첨부파일)
#   - 마감일 지난 과제 제출 차단, 중복 제출 방지
#   - 저장: apps.core.models.SUBMISSION 생성
#   - 템플릿: student/submission_form.html
#
# FR-005 (제출 내용 미리보기):
#   - 제출 전/후 내가 낸 내용 미리보기 (첨부파일 포함)
#
# 공통: 학생 권한 체크 데코레이터/믹스인, 로그인 필수
