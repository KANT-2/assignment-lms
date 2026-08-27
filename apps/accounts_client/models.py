# apps/accounts_client/models.py
# 공통 담당 전담 — 외부 계정/팀 DB 참조 (managed = False, 이 앱에서 마이그레이션 생성 안 함)
#
# 별도의 accounts DB 에 이미 존재하는 테이블을 읽기 전용으로 매핑
# settings 의 DATABASE_ROUTERS 가 이 모델들을 accounts DB 로 라우팅
#
# 여기에 들어갈 모델:
# - AccountsUser (Meta: managed=False, db_table="accounts_user")
#     - id, email, name, role(학생/튜터), is_active, date_joined ...
# - TeamsTeam   (Meta: managed=False, db_table="teams_team")
#     - id, name, ...
# - (필요 시) 팀-멤버 매핑 테이블 모델
#
# 주의:
# - 이 모델들로 write/save 하지 않는다 (읽기 전용)
# - 다른 앱은 이 모델을 직접 import 하지 말고 services.py 헬퍼를 통해 접근
