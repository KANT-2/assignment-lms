# 지각 제출 — 동작과 DB 매핑

**작성:** 튜터 B · 2026-09-04
관련: [assignment-lms-round-close.md](assignment-lms-round-close.md) · [assignment-lms-grading.md](assignment-lms-grading.md) · [assignment-lms-round-close-verification.md](assignment-lms-round-close-verification.md)

> 지각 제출이 **언제 점수에 반영되고 언제 안 되는지**, 그리고 그게 어느 테이블·컬럼과
> 연결되는지 정리한다. "마감 후 소프트 경고"(`feat/round-close-stale-warning`) 포함.

---

## 1. 두 가지 목적, 세 개의 창(window)

지각 제출은 목적이 둘이다:

| | 목적 | 반영 |
|---|---|---|
| (i) | **점수** (지각 감점 적용) | 회차 점수에 들어감 |
| (ii) | **학습 완주 · 튜터 피드백 · GitHub 기록** | 회차 점수엔 안 들어감 |

시간축을 셋으로 나눈다:

```
        과제 due_at        회차 평가기간 종료      튜터가 "점수 마감" 클릭
  ──────────┼────── W1 ──────────┼────── W2 ──────────┼────── W3 ──────────▶
   (정시)         지각·회차 안        회차 넘김·마감 전       마감 후
```

| 창 | 제출 시각 | 점수 반영 | 목적 |
|---|---|---|---|
| **W1** | `due_at < submitted_at ≤ 회차종료` | ✅ 지각 감점 적용 | (i) |
| **W2** | `회차종료 < submitted_at ≤ closed_at` | ✅ (튜터 클릭 시점에 존재하면 계산에 포함) | (i) |
| **W3** | `submitted_at > closed_at` | ❌ 스냅샷 동결. 재마감 안 하면 영영 | (ii) |

> W2는 튜터가 회차 종료 당일/익일에 바로 마감하는 운영이면 거의 안 생긴다.
> 규칙은 단순하게 "튜터 클릭 전까지 존재하면 반영".

---

## 2. 관련 DB 테이블 · 컬럼

### 우리 DB (`assignment_lms`)

| 테이블 | 컬럼 | 지각 제출과의 관계 |
|---|---|---|
| `assignment` | `due_at` (datetime) | **지각 판정 기준선.** `submitted_at > due_at` 이면 지각 |
| | `allow_late` (bool, 기본 True) | False면 `due_at` 이후 제출 **차단**. True면 무기한 접수 |
| | `late_penalty` (uint, 기본 0) | 지각 시 튜터 점수에서 뺄 고정 점수. **0이면 감점 없음** |
| | `is_required` / `is_team` / `weight_tier` | 점수 버킷·중요도 배수·하한 결정 |
| | `deleted_at` | 소프트 삭제. 채점 대상에서 제외 |
| `submission` | `submitted_at` (datetime, `auto_now_add`) | **제출 시각.** 재제출 시 갱신([views_result.py:179](../apps/student/views_result.py#L179)). 심을 때는 쿼리셋 `update()` 로 강제 |
| | `student_id` / `team_id` | 개인=student, 팀=team (배타). 팀 제출 1행이 팀원 전원에 상속 (BR-005) |
| | `is_locked` (bool) | `Evaluation` 최초 저장 시 True → 재제출 차단 |
| | `final_score` (int, nullable) | `Evaluation.score` 를 시그널로 캐시 ([core/signals.py](../apps/core/signals.py)). **지각 감점 미반영 원점수** |
| `evaluation` | `score` / `feedback` / `updated_at` | 튜터 공식 평가. 저장 시 `submission.final_score` + `is_locked` 동기화 |
| `grading_policy` | `required_floor`(40) / `optional_floor`(20) | 제출·채점 시 점수 하한 |
| | `required_miss_penalty`(10) | **미제출 필수 과제 점수** (← "0점 아님") |
| | `weight_high/mid/low`(1.5/1.0/0.5) | 중요도 배수 |
| | `achievement_weight`(0.7) / `sincerity_weight`(0.3) | 최종 = 성취도 0.7 + 성실성 0.3 |
| `round_score` | `round_id` + `student_id` (유니크) | **회차 × 학생 점수 스냅샷** |
| | `total` / `achievement` / `sincerity` | 마감 시점 계산값 박제 (AX2 전달값은 `total`) |
| | `assignment_ids` (JSON) | 그 마감에 집계된 과제 id 목록 |
| | `closed_at` / `closed_by` | 마감·재마감 시각 / 튜터 id |
| | `graded_count` / `ungraded_count` / `total_count` | 채점됨 / 제출·미채점 / 대상 과제 수 |

### 외부 DB (`ax_evaluation`, 읽기 전용)

| 뷰/테이블 | 컬럼 | 역할 |
|---|---|---|
| `rounds_evaluationround` (`EvaluationRound`, managed=False) | `id`, `status`, `evaluation_start_at`, `evaluation_end_at` | **회차 기간.** 과제가 어느 회차에 속하는지 결정 |
| `accounts.get_round_period(round_id)` | → `(start, end)` \| None | `evaluation_start_at/end_at` 읽음 |
| `accounts.get_previous_round_end(round_id)` | → datetime \| None | 직전 회차의 `evaluation_end_at` (스코프 하한) |

> **`assignment` 에 `round_id` 컬럼은 없다.** 회차 귀속은 `due_at` 을 회차 기간과
> 비교해 계산하고, 결과만 `round_score.assignment_ids` 에 박제한다.

---

## 3. 판정 규칙 (코드 지점)

### 3.1 제출 접수 여부 — `allow_late`

[views_submit.py:234](../apps/student/views_submit.py#L234), [:271](../apps/student/views_submit.py#L271) (트랜잭션 안에서 `select_for_update` 로 재확인 — race 방지)

```python
is_late = timezone.now() > assignment.due_at
if is_late and not assignment.allow_late:
    # → "마감되어 더 이상 제출할 수 없는 과제입니다"
```

### 3.2 지각 여부 — `submitted_at > due_at`

저장된 플래그 없음. 매번 계산. 경계는 **엄격 `>`** (정각 제출 = 정시).

| 화면 | 코드 |
|---|---|
| 학생 과제목록 "지각 제출완료" | [views_submit.py:131](../apps/student/views_submit.py#L131) |
| 튜터 제출현황 `RosterRow.is_late` | [views_manage.py](../apps/tutor/views_manage.py) `is_late` 프로퍼티 |
| 튜터 채점화면 "지각 제출" 뱃지 | [views_review.py:171](../apps/tutor/views_review.py#L171) |

### 3.3 재제출 — `due_at` 전까지만

[views_result.py:42](../apps/student/views_result.py#L42)

```python
if timezone.now() >= submission.assignment.due_at:
    return "재제출은 과제 마감 전까지만 가능합니다."
```

→ 지각 제출은 첫 제출 한 번으로 끝. 마감 후엔 수정 불가.

---

## 4. 점수 계산 — 창별

계산 진입점: [grading.py](../apps/tutor/grading.py) `compute()` → `_score_one()`

### 성취도 (achievement, 최종의 70%)

과제 1건당 점수 (`_score_one`, [grading.py:130-139](../apps/tutor/grading.py#L130)):

```python
if sub is None:                       # 미제출
    raw = policy.required_miss_penalty if a.is_required else 0   # 필수 10 / 선택 0
elif sub.final_score is None:         # 제출·미채점
    ungraded_count += 1               # 성취도 계산에서 제외
else:                                 # 제출·채점완료
    penalty = a.late_penalty if sub.submitted_at > a.due_at else 0
    raw = max(policy.floor_for(a.is_required), sub.final_score - penalty)
```

버킷 `(is_team, is_required)` 4개 → 중요도 배수 가중평균 → base 비중(개인:팀 7:3, 선택:필수 6:4) 정규화 합산.

### 성실성 (sincerity, 최종의 30%)

마감 지난 대상 과제 중 **제출한 비율** ([grading.py:12](../apps/tutor/grading.py#L12)).
**지각도 "제출"로 인정** — 성실성엔 지각 페널티 없음.

### 최종

```
최종 = 성취도 × 0.7 + 성실성 × 0.3
```

---

## 5. 회차 스코프 — `due_at` 기준

[grading.py:184](../apps/tutor/grading.py#L184) `scope_assignments(round_id)`

```
직전 회차 종료(get_previous_round_end)  <  due_at  ≤  이 회차 종료(get_round_period[1])
                                       AND  due_at < now
```

- 과제는 **정확히 한 회차에만** 속함 (경계는 `due_at`, `submitted_at` 아님)
- `get_round_period` 가 None → 마감 지난 전체 과제로 폴백
- 결과는 `round_score.assignment_ids` 에 박제

---

## 6. 마감 후 소프트 경고 (`feat/round-close-stale-warning`)

### 6.1 학생 — "점수 미반영"

[grading.py](../apps/tutor/grading.py) `closed_round_windows()` / `score_locked_close(assignment)`:

```python
# 마감된 적 있는 회차(RoundScore 존재)들의 스코프 창을 만들고
# assignment.due_at 이 그 안이면 (round_id, closed_at) 반환
```

| 조건 | 결과 |
|---|---|
| 과제 `due_at` 이 **마감된 회차** 스코프 안 | 🔒 잠김 → 학생 경고 + "점수 미반영" 배지 |
| **gap 과제** (`due_at` 이 마감된 회차 종료 이후) | 🔓 안 잠김 — 다음 회차 채점 대상 |
| `get_round_period` None | 🔓 안 잠김 (fail-open) |

- 제출 폼: "…지금 제출해도 회차 점수에는 반영되지 않습니다. 튜터 피드백은 받을 수 있습니다." ([submission_form.html](../apps/student/templates/student/submission_form.html))
- **제출은 막지 않는다.**

### 6.2 튜터 — "재마감 필요"

[views_round.py](../apps/tutor/views_round.py) `_preview()` `stale_count`:
실시간 `compute` 결과 ↔ `round_score` 스냅샷의 `total/achievement/sincerity`(소수 1자리) 비교
→ 달라진 학생 수. `> 0` 이면 점수집계 화면에 배너.

마감 후 신규 제출(W3), 마감 후 채점 완료 둘 다 잡힘.

### 6.3 회차가 넘어간 뒤

`round_close` 는 항상 `accounts.get_current_round()` 대상.
다음 회차가 `IN_PROGRESS` 가 되면 지난 회차는 UI 로 재마감 불가 → `manage.py shell` 수동.

---

## 7. 멀티라운드 누적

**누적 총점 없음.** 회차마다 `round_score` 행이 독립적으로 찍힌다.

```
회차 N: due_at ≤ END_N            → RoundScore(round_id=N)
gap:    END_N < due_at < START_N1  (아직 소속 회차 미마감)
회차 N+1: END_N < due_at ≤ END_N1  → RoundScore(round_id=N+1)   ※ gap 과제 포함
```

- 회차 N+1 채점 시 팀 구성은 `get_student_teams()` 가 **그 회차 round_id 로 재조회** → 재편성분 반영
- 옛 회차 과제(`due_at ≤ END_N`)는 N+1 스코프 하한(`prev_end = END_N`) 밖 → **안 들어감**
- 최종 학생 평가는 AX2 쪽에서 관리. 이 LMS 는 회차 단위 `total` 을 CSV 로 공급

테스트: [test_round_close.py](../apps/tutor/tests/test_round_close.py) `MultiRoundAccumulationTests`

---

## 8. 구체 예시 (`GradingPolicy` 기본값)

회차 61: 평가기간 ~ 08-27, `late_penalty=5` 인 필수 과제 A1 (튜터 점수 60 가정)

| 시나리오 | `submitted_at` | 계산 | A1 성취도 반영 |
|---|---|---|---|
| 정시 | 08-20 | `max(40, 60)` | **60** |
| **W1** 지각 | 08-24 | `max(40, 60 − 5)` | **55** |
| **W1** 지각, 낮은 점수 (튜터 30) | 08-24 | `max(40, 30 − 5)` | **40** (하한) |
| **W1** 지각, `late_penalty=0`인 과제 | 08-24 | `max(40, 60 − 0)` | **60** (감점 없음) |
| **W3** 마감(08-28) 후 제출, 미채점 | 09-02 | 마감 시점 = 미제출 필수 | **10** (동결) |
| **W3** + 튜터 재마감 (회차 61 아직 current) | 09-02, 채점 60 | `max(40, 60 − 5)` | **55** |
| **W3** + 회차 62 시작 후 (재마감 불가) | 09-02 | 회차 61 스냅샷 그대로 · 회차 62 스코프 밖 | **10** (영영) |

성실성: 위 모든 "제출" 케이스는 분자 +1 (지각·W3 무관). 미제출만 분모에만.

---

## 9. 엣지 케이스 요약

| 상황 | 결과 |
|---|---|
| 마감 정각 제출 | 지각 아님 (`>` 엄격) |
| 튜터가 마감을 날짜만 입력 (`00:00:00`) | 그날 종일이 지각 |
| `allow_late=False` + 지각 | 제출 차단 |
| `allow_late=True` + `late_penalty=0` + 지각 | 접수·시각 기록, 감점 0 |
| 팀원 1명 지각 제출 | 팀 제출 1행 → 팀원 전원 지각·감점 |
| 팀 미편성 (팀 과제) | 그 과제 성취도·성실성에서 통째 제외 |
| 마감 후 튜터가 `due_at` 을 미래로 수정 | 기존 지각들이 소급해서 정시로 (매번 재계산) |
| 채점 후 `late_penalty` 값 변경 | `round_score` 불변. 재마감해야 반영 |
| W3 제출 + 재마감 안 함 | 미제출 점수(필수 10 / 선택 0)로 동결 |
| gap 과제 W3 제출 | 다음 회차에서 정상 채점 |
| 옛 회차 과제 지각 제출 (회차 넘어간 뒤) | 어느 회차에도 안 잡힘 (orphan) |

---

## 10. 관련 파일

| 파일 | 역할 |
|---|---|
| [apps/core/models.py](../apps/core/models.py) | `Assignment` / `Submission` / `Evaluation` |
| [apps/core/signals.py](../apps/core/signals.py) | `Evaluation` → `Submission.final_score` / `is_locked` 동기화 |
| [apps/student/views_submit.py](../apps/student/views_submit.py) | 제출 접수 (`allow_late` 게이트), 목록 상태 |
| [apps/student/views_result.py](../apps/student/views_result.py) | 재제출 (마감 전까지) |
| [apps/tutor/grading.py](../apps/tutor/grading.py) | `compute` / `scope_assignments` / `snapshot` / `closed_round_windows` / `score_locked_close` |
| [apps/tutor/models.py](../apps/tutor/models.py) | `GradingPolicy` / `RoundScore` |
| [apps/tutor/views_round.py](../apps/tutor/views_round.py) | 회차 마감 · `_preview.stale_count` |
| [apps/accounts_client/services.py](../apps/accounts_client/services.py) | `get_round_period` / `get_previous_round_end` |
