"""
apps/accounts_client/services.py — 공통 담당 전담

외부 계정/팀 데이터 조회 헬퍼. **다른 앱은 이 함수들만 사용**한다
(accounts_client.models 를 직접 import 하지 말 것).

동작 모드:
- 평소: AX2 통합 플랫폼 VIEW(ax_evaluation DB)를 읽는다.
    · 신원/역할  → ax_user_team_login_view      (AxUserLogin)
    · 라운드별 팀 → user_round_team_view          (RoundTeamMember)
- settings.DEV_SKIP_AUTH=True: DB 없이 아래 가짜 데이터를 반환 (로컬 개발용).

우리 라운드 = settings.AX_ROUND_ID 있으면 그 값, 없으면 IN_PROGRESS 라운드,
그것도 없으면 가장 큰 round_id (라운드가 바뀌면 서버 재시작 필요 — _current_round_id 캐시).

반환 객체 계약 (소비 코드가 기대하는 최소 속성):
    user  → .id  .name  .email  .role("student"|"tutor"|"admin")
    team  → .id  .name  (.number)
"""
from datetime import datetime, time, timedelta
from functools import lru_cache
from types import SimpleNamespace

from django.conf import settings
from django.utils import timezone


def _dev() -> bool:
    return bool(getattr(settings, "DEV_SKIP_AUTH", False))


def _ns(**kw):
    return SimpleNamespace(**kw)


# ─────────────────────────────────────────────────────────────
# 개발용 가짜 데이터 (DEV_SKIP_AUTH=True 일 때만)
# ─────────────────────────────────────────────────────────────
_DEV_TUTOR = {"id": 1, "name": "김튜터", "email": "tutor@dev.local", "role": "tutor"}
_DEV_STUDENTS = [
    {"id": 11, "name": "김학생", "email": "s11@dev.local", "role": "student"},
    {"id": 12, "name": "이학생", "email": "s12@dev.local", "role": "student"},
    {"id": 13, "name": "박학생", "email": "s13@dev.local", "role": "student"},
    {"id": 14, "name": "최학생", "email": "s14@dev.local", "role": "student"},
    {"id": 15, "name": "정학생", "email": "s15@dev.local", "role": "student"},
]
_DEV_TEAMS = [{"id": 1, "name": "1팀", "number": 1}, {"id": 2, "name": "2팀", "number": 2}]
_DEV_TEAM_MEMBERS = {1: [11, 12, 13], 2: [14, 15]}
_DEV_USERS_BY_ID = {u["id"]: u for u in [_DEV_TUTOR, *_DEV_STUDENTS]}


# ─────────────────────────────────────────────────────────────
# 우리 라운드 선택
# ─────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _current_round_id():
    override = getattr(settings, "AX_ROUND_ID", None)
    if override:
        return int(override)
    from .models import RoundTeamMember

    qs = RoundTeamMember.objects.all()
    rid = (
        qs.filter(round_status="IN_PROGRESS")
        .order_by("-round_id")
        .values_list("round_id", flat=True)
        .first()
    )
    if rid is None:
        rid = qs.order_by("-round_id").values_list("round_id", flat=True).first()
    return rid


# ─────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────
def get_user(user_id):
    """단일 사용자 (없으면 None). role/email 이 필요하면 이걸 쓴다."""
    if _dev():
        d = _DEV_USERS_BY_ID.get(int(user_id))
        return _ns(**d) if d else None
    from .models import AxUserLogin

    row = AxUserLogin.objects.filter(pk=user_id).first()
    return _user_ns(row) if row else None


def get_users(user_ids):
    """여러 사용자 → {user_id: user}."""
    ids = [int(i) for i in user_ids]
    if _dev():
        return {i: _ns(**_DEV_USERS_BY_ID[i]) for i in ids if i in _DEV_USERS_BY_ID}
    from .models import AxUserLogin

    return {r.user_id: _user_ns(r) for r in AxUserLogin.objects.filter(pk__in=ids)}


def get_students():
    """승인된 활성 학생 전체 (제출률 분모 · 미제출자 명단용)."""
    if _dev():
        return [_ns(**u) for u in _DEV_STUDENTS]
    from .models import AxUserLogin

    rows = AxUserLogin.objects.filter(
        role="student", is_active=True, approval_status="approved"
    ).order_by("display_name_snapshot", "first_name")
    return [_user_ns(r) for r in rows]


def get_teams():
    """우리 라운드의 전체 팀 (team_number 순)."""
    if _dev():
        return [_ns(**t) for t in _DEV_TEAMS]
    from .models import RoundTeamMember

    seen = {}
    for r in RoundTeamMember.objects.filter(round_id=_current_round_id()).order_by(
        "team_number"
    ):
        seen.setdefault(r.team_id, _ns(id=r.team_id, name=r.team_name, number=r.team_number))
    return list(seen.values())


def get_team_members(team_id):
    """우리 라운드에서 그 팀에 속한 학생 목록."""
    team_id = int(team_id)
    if _dev():
        return [_ns(**_DEV_USERS_BY_ID[uid]) for uid in _DEV_TEAM_MEMBERS.get(team_id, [])]
    from .models import RoundTeamMember

    rows = RoundTeamMember.objects.filter(
        round_id=_current_round_id(), team_id=team_id
    ).order_by("display_name_snapshot")
    return [_ns(id=r.user_id, name=r.name, email=r.email, role="student") for r in rows]


def get_user_team(user_id):
    """사용자가 우리 라운드에서 속한 팀 (없으면 None)."""
    user_id = int(user_id)
    if _dev():
        for tid, members in _DEV_TEAM_MEMBERS.items():
            if user_id in members:
                return _ns(**next(t for t in _DEV_TEAMS if t["id"] == tid))
        return None
    from .models import RoundTeamMember

    r = RoundTeamMember.objects.filter(
        round_id=_current_round_id(), user_id=user_id
    ).first()
    return _ns(id=r.team_id, name=r.team_name, number=r.team_number) if r else None


def get_student_teams():
    """우리 라운드 전체의 {user_id: team} 매핑 (학생 목록 화면용 · 1쿼리)."""
    if _dev():
        out = {}
        for tid, members in _DEV_TEAM_MEMBERS.items():
            t = next(x for x in _DEV_TEAMS if x["id"] == tid)
            for uid in members:
                out[uid] = _ns(**t)
        return out
    from .models import RoundTeamMember

    return {
        r.user_id: _ns(id=r.team_id, name=r.team_name, number=r.team_number)
        for r in RoundTeamMember.objects.filter(round_id=_current_round_id())
    }


def get_current_round():
    """우리 라운드 (없으면 None). .id / .title — GitHub 저장소 폴더명 등에 쓴다."""
    if _dev():
        return _ns(id=1, title="개발기수")
    from .models import RoundTeamMember

    rid = _current_round_id()
    if rid is None:
        return None
    title = (
        RoundTeamMember.objects.filter(round_id=rid)
        .values_list("round_title", flat=True)
        .first()
    )
    return _ns(id=rid, title=title or f"round-{rid}")


def get_round_period(round_id=None):
    """회차의 (평가 시작, 평가 종료) datetime 튜플. 못 구하면 None.
    회차 점수 마감(docs/assignment-lms-round-close.md)에서 과제 스코프 산정에 쓴다."""
    if _dev():
        now = timezone.now()
        return (now - timedelta(days=14), now + timedelta(days=1))
    from .models import EvaluationRound

    rid = round_id or _current_round_id()
    if rid is None:
        return None
    row = (
        EvaluationRound.objects.filter(pk=rid)
        .values_list("evaluation_start_at", "evaluation_end_at")
        .first()
    )
    if not row or row[1] is None:
        return None
    return row


def get_team_period(round_id=None):
    """회차의 팀 프로젝트 (시작, 종료) datetime 튜플. 못 구하면 None.

    user_round_team_view 의 team_start / team_end (date, 라운드별 동일)를 읽어
    시작=그날 00:00, 종료=그날 23:59:59 (로컬 타임존)로 돌려준다.
    팀 과제 마감일 상한 검증(AssignmentForm)에서 쓴다.
    """
    if _dev():
        now = timezone.localtime()
        return (now - timedelta(days=30), now + timedelta(days=60))
    from .models import RoundTeamMember

    rid = round_id or _current_round_id()
    if rid is None:
        return None
    row = (
        RoundTeamMember.objects.filter(round_id=rid)
        .values_list("team_start", "team_end")
        .first()
    )
    if not row or row[0] is None or row[1] is None:
        return None
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(row[0], time.min), tz)
    end = timezone.make_aware(datetime.combine(row[1], time.max), tz)
    return (start, end)


def get_previous_round_end(round_id=None):
    """이 회차 직전 회차의 평가 종료 datetime. 없으면(첫 회차) None.
    과제 스코프 하한: 직전 회차 종료 < due_at ≤ 이 회차 종료."""
    if _dev():
        return None
    from .models import EvaluationRound

    rid = round_id or _current_round_id()
    period = get_round_period(rid)
    if rid is None or period is None:
        return None
    return (
        EvaluationRound.objects.filter(evaluation_end_at__lt=period[1])
        .exclude(pk=rid)
        .order_by("-evaluation_end_at")
        .values_list("evaluation_end_at", flat=True)
        .first()
    )


def is_team_member(user_id, team_id):
    """팀 과제 제출 자격 — 우리 라운드에서 그 팀 소속인지 (BR-005)."""
    user_id, team_id = int(user_id), int(team_id)
    if _dev():
        return user_id in _DEV_TEAM_MEMBERS.get(team_id, [])
    from .models import RoundTeamMember

    return RoundTeamMember.objects.filter(
        round_id=_current_round_id(), user_id=user_id, team_id=team_id
    ).exists()


def is_tutor(user_id):
    # 개발 모드: 역할 게이트를 열어 둔다 (DEV_ROLE 무관, 화면 확인용). 사이드바만 DEV_ROLE.
    if _dev():
        return True
    u = get_user(user_id)
    return bool(u and u.role == "tutor")


def is_student(user_id):
    if _dev():
        return True
    u = get_user(user_id)
    return bool(u and u.role == "student")


# ─────────────────────────────────────────────────────────────
def _user_ns(row):
    """AxUserLogin → 계약 객체."""
    return _ns(id=row.user_id, name=row.name, email=row.email, role=row.role)
