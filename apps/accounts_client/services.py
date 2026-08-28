"""
apps/accounts_client/services.py — 공통 담당 전담

외부 계정/팀 데이터 조회 헬퍼. **다른 앱은 이 함수들만 사용**한다
(accounts_client.models 를 직접 import 하지 말 것).

동작 모드:
- 평소: 외부 `accounts` DB (AX Evaluator) 의 managed=False 모델을 읽는다.
- settings.DEV_SKIP_AUTH=True: `accounts` DB 없이 아래 가짜 데이터를 반환한다
  (로그인 방식 확정 전 개발용). settings.DEV_ROLE 로 현재 사용자 역할을 정한다.

반환 객체는 최소한 다음 속성을 갖는다:
    user  → .id  .name  .email  .role("STUDENT"|"TUTOR")
    team  → .id  .name
"""
from types import SimpleNamespace

from django.conf import settings


def _dev() -> bool:
    return bool(getattr(settings, "DEV_SKIP_AUTH", False))


# ─────────────────────────────────────────────────────────────
# 개발용 가짜 데이터 (DEV_SKIP_AUTH=True 일 때만 사용)
# ─────────────────────────────────────────────────────────────
_DEV_TUTOR = {"id": 1, "name": "김튜터", "email": "tutor@dev.local", "role": "TUTOR"}
_DEV_STUDENTS = [
    {"id": 11, "name": "김학생", "email": "s11@dev.local", "role": "STUDENT"},
    {"id": 12, "name": "이학생", "email": "s12@dev.local", "role": "STUDENT"},
    {"id": 13, "name": "박학생", "email": "s13@dev.local", "role": "STUDENT"},
    {"id": 14, "name": "최학생", "email": "s14@dev.local", "role": "STUDENT"},
    {"id": 15, "name": "정학생", "email": "s15@dev.local", "role": "STUDENT"},
]
_DEV_TEAMS = [{"id": 1, "name": "1팀"}, {"id": 2, "name": "2팀"}]
_DEV_TEAM_MEMBERS = {1: [11, 12, 13], 2: [14, 15]}

_DEV_USERS_BY_ID = {u["id"]: u for u in [_DEV_TUTOR, *_DEV_STUDENTS]}


def _ns(d):
    return SimpleNamespace(**d)


# ─────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────
def get_user(user_id):
    """단일 사용자 (없으면 None)."""
    if _dev():
        d = _DEV_USERS_BY_ID.get(int(user_id))
        return _ns(d) if d else None
    from .models import AccountsUser
    return AccountsUser.objects.filter(pk=user_id).first()


def get_users(user_ids):
    """여러 사용자 → {id: user}."""
    ids = [int(i) for i in user_ids]
    if _dev():
        return {i: _ns(_DEV_USERS_BY_ID[i]) for i in ids if i in _DEV_USERS_BY_ID}
    from .models import AccountsUser
    return {u.id: u for u in AccountsUser.objects.filter(pk__in=ids)}


def get_students():
    """role=STUDENT, is_active 인 전체 학생 (제출률 분모·미제출자 명단용)."""
    if _dev():
        return [_ns(u) for u in _DEV_STUDENTS]
    from .models import AccountsUser
    return list(AccountsUser.objects.filter(role="STUDENT", is_active=True).order_by("name"))


def get_teams():
    """이 강의의 전체 팀."""
    if _dev():
        return [_ns(t) for t in _DEV_TEAMS]
    from .models import TeamsTeam
    return list(TeamsTeam.objects.all().order_by("name"))


def get_team_members(team_id):
    """팀 소속 멤버 목록."""
    team_id = int(team_id)
    if _dev():
        return [_ns(_DEV_USERS_BY_ID[uid]) for uid in _DEV_TEAM_MEMBERS.get(team_id, [])]
    from .models import AccountsUser, TeamsTeamMembership
    member_ids = TeamsTeamMembership.objects.filter(team_id=team_id).values_list("user_id", flat=True)
    return list(AccountsUser.objects.filter(pk__in=list(member_ids)).order_by("name"))


def get_user_team(user_id):
    """사용자가 속한 팀 (없으면 None). 개인은 여러 팀일 수 없다고 가정."""
    user_id = int(user_id)
    if _dev():
        for tid, members in _DEV_TEAM_MEMBERS.items():
            if user_id in members:
                return _ns(next(t for t in _DEV_TEAMS if t["id"] == tid))
        return None
    from .models import TeamsTeam, TeamsTeamMembership
    m = TeamsTeamMembership.objects.filter(user_id=user_id).first()
    return TeamsTeam.objects.filter(pk=m.team_id).first() if m else None


def is_team_member(user_id, team_id):
    """팀 과제 제출 자격 — 그 팀 소속인지 (BR-005)."""
    user_id, team_id = int(user_id), int(team_id)
    if _dev():
        return user_id in _DEV_TEAM_MEMBERS.get(team_id, [])
    from .models import TeamsTeamMembership
    return TeamsTeamMembership.objects.filter(team_id=team_id, user_id=user_id).exists()


def is_tutor(user_id):
    # 개발 모드에서는 역할 게이트를 열어 둔다: DEV_ROLE 과 무관하게 튜터/학생 화면을
    # 모두 볼 수 있게 한다 (화면 확인용). 사이드바 메뉴만 DEV_ROLE 로 갈린다.
    if _dev():
        return True
    u = get_user(user_id)
    return bool(u and u.role == "TUTOR")


def is_student(user_id):
    if _dev():
        return True
    u = get_user(user_id)
    return bool(u and u.role == "STUDENT")
