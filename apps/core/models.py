# apps/core/models.py
# ⚠ 공통 담당 전담 — 이 프로젝트의 공유 모델. 학생/튜터팀은 여기 수정 금지 (요청만)
#
# 이 프로젝트 전용 PostgreSQL DB 에 실제로 생성되는 테이블 (managed=True)
# ERD: docs/assignment-system-erd-v5.mermaid 참고
#
# 여기에 들어갈 모델:
# - LECTURE      : 강의 (외부 강의 데이터를 이 시스템에서 참조하기 위한 최소 정보)
# - ASSIGNMENT   : 과제
#     - 소속 강의(LECTURE), 제목, 설명, 마감일, 재제출 허용 여부, 상태(공개/비공개)
#     - 생성/수정 튜터, created_at / updated_at
# - SUBMISSION   : 과제 제출물
#     - ASSIGNMENT FK, 제출 학생(accounts_user id), 본문/첨부파일, 제출일시
#     - 차수(재제출 회차), 상태(제출/재제출요청/완료)
# - EVALUATION   : 평가 결과
#     - SUBMISSION FK (1:1), 평가 튜터, 점수/피드백, 통과 여부, 평가일시
#
# 공통 사항:
# - 생성/수정 시각 공용 추상 모델(TimeStampedModel) 정의 후 상속 고려
# - 사용자/팀은 FK 로 직접 잇지 않고 id 값만 저장 → apps.accounts_client 로 조회
