# apps/accounts_client/services.py
# 공통 담당 전담 — 외부 계정/팀 데이터 조회 헬퍼. 다른 앱은 이 함수들만 사용
#
# 여기에 들어갈 함수:
# - get_user(user_id)            : 단일 사용자 조회 (없으면 None)
# - get_users(user_ids)          : 여러 사용자 한 번에 조회 → {id: user}
# - get_team_members(team_id)    : 팀 소속 멤버 목록
# - get_user_team(user_id)       : 사용자가 속한 팀
# - is_tutor(user_id) / is_student(user_id) : 역할 확인
#
# 조회 결과 캐싱 고려 (요청 단위)
