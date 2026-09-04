"""
apps/tutor/grading.py — 학생별 최종 점수 산출.

최종 점수 = 과제 성취도 × 0.7 + 성실성(제출률) × 0.3   (비중은 GradingPolicy)

성취도: 개인·필수 / 개인·선택 / 팀·필수 / 팀·선택 4개 영역.
  · 영역점수 = Σ(과제점수 × 중요도) / Σ(중요도)      중요도: 상 1.5 / 중 1.0 / 하 0.5
  · 과제점수 — 미제출 필수 10, 미제출 선택 0,
               제출·채점완료 = max(floor, 튜터점수 − 지각감점)  (floor: 필수 40 / 선택 20)
               제출·미채점 = 성취도 계산에서 제외 (+ "미채점 N건" 안내)
  · 영역 비중 개인:팀 = 7:3, 선택:필수 = 6:4 → 빈 영역은 재정규화로 제외
성실성: 마감 지난 대상 과제 중 제출한 비율 (지각도 제출로 인정).

- 마감 지난(due_at < now) · 삭제 안 된 과제만 대상.
- 팀 과제는 학생 팀의 제출물/평가를 상속 (BR-005). 팀이 없으면 팀 과제는 전부 제외.
- 실시간 계산 — 저장하지 않는다.

회차 점수 마감(docs/assignment-lms-round-close.md): scope_assignments() 로 회차 과제를
추려 compute(..., assignments=scope) 한 뒤 snapshot() 이 RoundScore 로 박제한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.accounts_client import services as accounts
from apps.core.models import Assignment, Submission

from .models import GradingPolicy, RoundScore


@dataclass
class StudentScore:
    final: float | None = None            # 0~100, 소수 1자리. None = 산출 불가
    achievement: float | None = None      # 과제 성취도 (0~100)
    sincerity: float | None = None        # 성실성/제출률 (0~100)
    graded_count: int = 0                 # 채점 완료된 대상 과제 수
    ungraded_count: int = 0               # 제출했으나 미채점 → 성취도에서 제외된 수
    total_count: int = 0                  # 마감 지난 대상 과제 수


@dataclass
class _Bucket:
    weighted_sum: float = 0.0
    weight_total: float = 0.0

    def add(self, score: float, weight: float) -> None:
        self.weighted_sum += score * weight
        self.weight_total += weight

    @property
    def empty(self) -> bool:
        return self.weight_total <= 0

    @property
    def score(self) -> float:
        return self.weighted_sum / self.weight_total


def compute(student_ids, *, now=None, assignments=None) -> dict[int, StudentScore]:
    """{student_id: StudentScore}. 존재하지 않는 학생은 빈 StudentScore.

    assignments=None  → 마감 지난 전체 과제 (기존 동작, 실시간 조회용).
    assignments=[...]  → 그 과제 목록만 대상 (회차 점수 마감 — 회차 스코프).
    """
    student_ids = list(dict.fromkeys(int(s) for s in student_ids))
    now = now or timezone.now()
    policy = GradingPolicy.get_solo()

    if assignments is None:
        assignments = list(Assignment.objects.filter(due_at__lt=now))
    else:
        assignments = list(assignments)
    if not assignments:
        return {sid: StudentScore() for sid in student_ids}

    a_ids = [a.id for a in assignments]
    teams = _safe_student_teams()

    # (student_id, assignment_id) → Submission,  (team_id, assignment_id) → Submission
    personal: dict[tuple[int, int], Submission] = {}
    team_subs: dict[tuple[int, int], Submission] = {}
    for s in Submission.objects.filter(assignment_id__in=a_ids):
        if s.student_id is not None:
            personal[(s.student_id, s.assignment_id)] = s
        elif s.team_id is not None:
            team_subs[(s.team_id, s.assignment_id)] = s

    out: dict[int, StudentScore] = {}
    for sid in student_ids:
        out[sid] = _score_one(sid, teams.get(sid), assignments, personal, team_subs, policy, now)
    return out


def _safe_student_teams() -> dict:
    try:
        return accounts.get_student_teams() or {}
    except Exception:  # noqa: BLE001 — 팀 조회 실패 시 전원 팀 없음으로 취급
        return {}


def _score_one(sid, team, assignments, personal, team_subs, policy: GradingPolicy, now) -> StudentScore:
    result = StudentScore()

    # 4개 영역: buckets[is_team][is_required]
    buckets = {
        (False, True): _Bucket(), (False, False): _Bucket(),
        (True, True): _Bucket(), (True, False): _Bucket(),
    }
    submitted = applicable = 0

    for a in assignments:
        if a.is_team:
            if team is None:
                continue  # 팀 없음 → 팀 과제 전부 제외 (성취도·성실성 모두)
            sub = team_subs.get((team.id, a.id))
        else:
            sub = personal.get((sid, a.id))

        applicable += 1
        result.total_count += 1
        if sub is not None:
            submitted += 1

        w = policy.tier_multiplier(a.weight_tier)
        bucket = buckets[(a.is_team, a.is_required)]

        if sub is None:
            raw = policy.required_miss_penalty if a.is_required else 0
            bucket.add(raw, w)
        elif sub.final_score is None:
            result.ungraded_count += 1  # 미채점 → 성취도 제외
        else:
            result.graded_count += 1
            penalty = a.late_penalty if sub.submitted_at > a.due_at else 0
            raw = max(policy.floor_for(a.is_required), sub.final_score - penalty)
            bucket.add(raw, w)

    result.achievement = _achievement(buckets, policy)
    result.sincerity = round(submitted / applicable * 100, 4) if applicable else None

    if result.achievement is None:
        result.final = None
    else:
        aw, sw = policy.major_weights
        sincerity = result.sincerity if result.sincerity is not None else 0.0
        result.final = round(result.achievement * aw + sincerity * sw, 1)
    return result


def _achievement(buckets: dict, policy: GradingPolicy) -> float | None:
    ind_w, team_w = policy.individual_team_weights
    opt_w, req_w = policy.optional_required_weights
    base = {
        (False, True): ind_w * req_w,
        (False, False): ind_w * opt_w,
        (True, True): team_w * req_w,
        (True, False): team_w * opt_w,
    }
    live = {key: base[key] for key, b in buckets.items() if not b.empty}
    total = sum(live.values())
    if total <= 0:
        return None
    return round(
        sum(buckets[key].score * (weight / total) for key, weight in live.items()), 4
    )


# =========================================================
# 회차 점수 마감 (docs/assignment-lms-round-close.md)
# =========================================================

@dataclass
class SnapshotResult:
    scores: list = field(default_factory=list)        # list[RoundScore]
    assignments: list = field(default_factory=list)   # 집계 대상 Assignment
    team_included: bool = False
    student_count: int = 0
    ungraded_total: int = 0                            # 전 학생 미채점 합


def scope_assignments(round_id, *, now=None) -> list[Assignment]:
    """이 회차에 귀속되는 과제: 직전 회차 종료 < due_at ≤ 이 회차 종료, 미삭제, 이미 마감(now 이전).

    회차 기간 정보를 못 구하면 마감 지난 전체 과제로 폴백한다 (튜터가 확인 화면에서 조정).
    """
    now = now or timezone.now()
    period = accounts.get_round_period(round_id)
    if period is None:
        return list(Assignment.objects.filter(due_at__lt=now))

    end = period[1]
    qs = Assignment.objects.filter(due_at__lte=end, due_at__lt=now)
    prev_end = accounts.get_previous_round_end(round_id)
    if prev_end is not None:
        qs = qs.filter(due_at__gt=prev_end)
    return list(qs.order_by("due_at"))


def scored_assignment_ids() -> set[int]:
    """이미 마감된 회차 스냅샷(RoundScore)에 **실제로 집계된** 과제 id 집합.

    회차 스코프 규칙을 다시 계산하지 않고, 박제된 `RoundScore.assignment_ids` 를 신뢰한다
    → 튜터가 확인 화면에서 제외한 과제는 포함되지 않고(정확), 경계·시각 엣지케이스도 없다.
    """
    ids: set[int] = set()
    for raw in RoundScore.objects.values_list("assignment_ids", flat=True):
        ids.update(raw or [])
    return ids


def score_locked_close(assignment, *, scored_ids=None) -> bool:
    """assignment 이 이미 마감된 회차에서 집계됐으면 True.

    학생 뷰에서 "이 회차는 점수 집계가 마감됐다 → 지금 제출해도 회차 점수 미반영" 경고에 쓴다.
    gap 과제(마감된 회차~새 회차 사이 생성)는 어느 스냅샷에도 없으니 False → 다음 회차에서 채점.
    목록처럼 여러 번 호출할 땐 scored_assignment_ids() 를 한 번 구해 넘긴다.
    """
    ids = scored_ids if scored_ids is not None else scored_assignment_ids()
    return assignment.id in ids


def _team_included(assignments, teams: dict) -> bool:
    """팀 과제가 스코프에 있고 팀 편성 데이터가 있으면 True.
    팀 과제가 없으면(반영할 게 없음) True. 팀 과제는 있는데 팀이 없으면 False → 재마감 필요."""
    has_team_assignment = any(a.is_team for a in assignments)
    if not has_team_assignment:
        return True
    return any(t for t in teams.values())


def snapshot(round_obj, closed_by, *, assignment_ids=None, now=None) -> SnapshotResult:
    """이번 회차 점수를 계산해 RoundScore 로 박제한다. 재마감이면 (round_id, student_id) 덮어쓰기.

    round_obj : accounts.get_current_round() 반환값 (.id / .title).
    closed_by : 마감 실행 튜터의 accounts_user.id.
    assignment_ids : 튜터가 확인 화면에서 조정한 과제 id 목록 (None 이면 scope_assignments 전체).
    """
    now = now or timezone.now()
    students = list(accounts.get_students() or [])

    assignments = scope_assignments(round_obj.id, now=now)
    if assignment_ids is not None:
        allowed = {int(i) for i in assignment_ids}
        assignments = [a for a in assignments if a.id in allowed]

    teams = _safe_student_teams()
    team_included = _team_included(assignments, teams)

    scores = compute([s.id for s in students], now=now, assignments=assignments)
    a_ids = [a.id for a in assignments]
    policy_snap = GradingPolicy.get_solo().as_snapshot()

    rows = []
    ungraded_total = 0
    with transaction.atomic():
        for stu in students:
            sc = scores.get(stu.id) or StudentScore()
            ungraded_total += sc.ungraded_count
            row, _ = RoundScore.objects.update_or_create(
                round_id=round_obj.id,
                student_id=stu.id,
                defaults={
                    "round_title": getattr(round_obj, "title", "") or "",
                    "student_name": getattr(stu, "name", "") or "",
                    "total": sc.final,
                    "achievement": sc.achievement,
                    "sincerity": sc.sincerity,
                    "team_included": team_included,
                    "graded_count": sc.graded_count,
                    "ungraded_count": sc.ungraded_count,
                    "total_count": sc.total_count,
                    "breakdown": {},
                    "assignment_ids": a_ids,
                    "policy_snapshot": policy_snap,
                    "closed_at": now,
                    "closed_by": int(closed_by),
                },
            )
            rows.append(row)

    return SnapshotResult(
        scores=rows,
        assignments=assignments,
        team_included=team_included,
        student_count=len(students),
        ungraded_total=ungraded_total,
    )
