# apps/core/models.py
# ⚠ 공통 담당 전담 — 이 프로젝트의 공유 모델. 학생/튜터팀은 여기 수정 금지 (요청만)
#
# 이 프로젝트 전용 PostgreSQL DB 에 실제로 생성되는 테이블 (managed=True)
# ERD: docs/assignment-lms-ERD.md 참고
#
# 여기에 들어갈 모델 (상세: docs/assignment-lms-ERD.md):
# - LECTURE          : 강의. 단일 강의 운영이라 사실상 1행 (BR-001)
# - LESSON           : 강의 1회차(수업). 튜터가 제목/수업날짜/블로그링크 + 교안 업로드,
#                      수업 종료 후 유튜브 링크 추가 (FR-015, FR-016)
#     - lecture FK, title, lesson_date, blog_url, created_by(튜터 id)
#     - video_url(유튜브, NULL 허용), video_thumbnail_url(미지정 시 video id로 자동생성),
#       video_published_at(NULL이면 아직 영상 없음)
# - LESSON_MATERIAL  : 강의 교안(복수). kind(FILE/LINK), title, file 또는 url, sort_order
# - ASSIGNMENT       : 과제
#     - lecture FK, 제목, 설명, due_at(마감), is_required(필수/선택),
#       allow_late(지각 허용), assignment_type(INDIVIDUAL/TEAM), created_by(튜터 id)
#     - deleted_at : 소프트 삭제 → 삭제 undo 지원 (FR-002)
# - SUBMISSION       : 제출물. (assignment, 제출단위) 당 1행, 재제출은 덮어쓰기(이력 미보관, FR-006)
#     - assignment FK
#     - student_id XOR team_id : 개인 과제는 student_id만, 팀 과제는 team_id만 (정확히 하나)
#     - description, is_late(제출 시점 마감 초과 — 튜터 배지용, BR-004), submitted_at
#     - is_locked : 튜터 공식 평가 저장 시 true → 재제출 차단 (BR-006)
#     - final_score : EVALUATION.score 캐시. NULL=피드백 대기 / 값=피드백 완료
#     - UNIQUE(assignment, student) / UNIQUE(assignment, team) 조건부 제약
#     - CHECK: student_id, team_id 중 정확히 하나만 non-null
# - SUBMISSION_FILE  : 제출 첨부파일(복수 가능)
#     - submission FK, file, original_name, size_bytes, content_type
#     - kind(PY/IPYNB/OTHER) → 미리보기 분기 (FR-005)
# - AI_EVALUATION    : AI 1차 평가. submission 1:1, 재생성 시 덮어쓰기 (FR-012)
#     - score(0~100), comment, is_simulated(현재 항상 True), model_name, regenerated_count, generated_at
# - EVALUATION       : 튜터 공식 평가. submission 1:1 (FR-013). 점수의 source of truth
#     - evaluator_id(튜터), score(0~100), feedback, created_at, updated_at(수정 가능)
#     - save() 시 SUBMISSION.final_score / is_locked 자동 동기화 (사람이 두 곳에 입력 안 함)
# - TODO             : 학생 개인 할 일 (대시보드 위젯, PRD 7장). student_id, content, due_date, is_done
#                      학생 전용이라 apps/student/models.py 로 빼도 무방
#
# 공통 사항:
# - 생성/수정 시각 공용 추상 모델(TimeStampedModel) 정의 후 상속 고려
# - score / final_score 는 CHECK 제약으로 0~100 제한 (BR-007)
# - 사용자/팀은 FK 로 직접 잇지 않고 id 값(정수)만 저장 → apps.accounts_client 로 조회
# - 테이블명은 lms_ 접두어 권장 (Meta.db_table) — 외부 스키마와 혼동 방지
