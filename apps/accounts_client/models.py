# apps/accounts_client/models.py
# 공통 담당 전담 — 외부 계정/팀 DB 참조 (managed = False, 이 앱에서 마이그레이션 생성 안 함)
#
# 별도의 accounts DB 에 이미 존재하는 테이블을 읽기 전용으로 매핑
# settings 의 DATABASE_ROUTERS 가 이 모델들을 accounts DB 로 라우팅
#
# 여기에 들어갈 모델 (상세: docs/assignment-lms-ERD.md):
# - AccountsUser (Meta: managed=False, db_table="accounts_user")
#     - id, email, name, role("STUDENT" | "TUTOR"), is_active, date_joined ...
# - TeamsTeam   (Meta: managed=False, db_table="teams_team")
#     - id, name, ...
# - TeamsTeamMembership (Meta: managed=False, db_table="teams_team_membership") — 팀-학생 매핑
#     - team_id, user_id
#     - is_representative(팀장 여부 — AX Evaluator에 필드 추가 요청중, 팀당 true 1명. PRD 9장 / 논의정리 §3)
#       → 승인 전제로 v6 작성. 거절 시 우리 쪽 TEAM_REPRESENTATIVE 테이블(v4)로 폴백
#     - 실제 컬럼은 AX Evaluator 스키마 확인 후 확정
#
# 주의:
# - 이 모델들로 write/save 하지 않는다 (읽기 전용)
# - 다른 앱은 이 모델을 직접 import 하지 말고 services.py 헬퍼를 통해 접근
