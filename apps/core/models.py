# apps/core/models.py
# ⚠ 공통 담당 전담 — 이 프로젝트의 공유 모델. 학생/튜터팀은 여기 수정 금지 (요청만)
#
# 이 프로젝트 전용 PostgreSQL DB 에 실제로 생성되는 테이블 (managed=True)
# ERD: docs/assignment-system-erd-v5.mermaid 참고
#
# 여기에 들어갈 모델 (상세: docs/assignment-lms-ERD.md):
# - LECTURE          : 강의. 단일 강의 운영이라 사실상 1행 (BR-001)
# - ASSIGNMENT       : 과제
#     - lecture FK, 제목, 설명, due_at(마감), is_required(필수/선택),
#       allow_late(지각 허용), assignment_type(INDIVIDUAL/TEAM), created_by(튜터 id)
#     - deleted_at : 소프트 삭제 → 삭제 undo 지원 (FR-002)
# - SUBMISSION       : 제출물. (assignment, 제출단위) 당 1행, 재제출은 덮어쓰기(이력 미보관, FR-006)
#     - assignment FK, submitter_id(학생/팀대표), team_id(팀 과제만), description
#     - is_late(제출 시점 마감 초과 — 튜터 배지용, BR-004), submitted_at
#     - locked_at(튜터 평가 저장 시각 → 재제출 잠금, BR-006)
#     - UNIQUE(assignment, submitter) / UNIQUE(assignment, team) 조건부 제약
# - SUBMISSION_FILE  : 제출 첨부파일(복수 가능)
#     - submission FK, file, original_name, size_bytes, content_type
#     - kind(PY/IPYNB/OTHER) → 미리보기 분기 (FR-005)
# - AI_EVALUATION    : AI 1차 평가. submission 1:1, 재생성 시 덮어쓰기 (FR-012)
#     - score(0~100), comment, is_simulated(현재 항상 True), model_name, generated_at
# - EVALUATION       : 튜터 공식 평가. submission 1:1 (FR-013)
#     - evaluator_id(튜터), score(0~100), feedback, created_at, updated_at(수정 가능)
#
# 공통 사항:
# - 생성/수정 시각 공용 추상 모델(TimeStampedModel) 정의 후 상속 고려
# - score 는 CHECK 제약으로 0~100 제한 (BR-007)
# - 사용자/팀은 FK 로 직접 잇지 않고 id 값(정수)만 저장 → apps.accounts_client 로 조회
