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
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from apps.accounts_client import services as accounts
from apps.core.models import Assignment, Submission

from .models import GradingPolicy


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


def compute(student_ids, *, now=None) -> dict[int, StudentScore]:
    """{student_id: StudentScore}. 존재하지 않는 학생은 빈 StudentScore."""
    student_ids = list(dict.fromkeys(int(s) for s in student_ids))
    now = now or timezone.now()
    policy = GradingPolicy.get_solo()

    assignments = list(Assignment.objects.filter(due_at__lt=now))
    if not assignments:
        return {sid: StudentScore() for sid in student_ids}

    a_ids = [a.id for a in assignments]
    teams = _safe_student_teams()
    team_ids = {t.id for t in teams.values() if t}

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
