# 회차 점수 마감 (튜터 트리거) v1

**작성:** 2026-09-01 · **구현 예정:** `apps/tutor/grading.py` · `apps/tutor/models.py::RoundScore` · `apps/accounts_client`
**담당:** 튜터 B · **적용 범위:** 튜터 전용 (학생 비노출)

> `apps/tutor/grading.py::compute()` 는 학생별 종합 점수를 **매 조회 시 실시간 계산**한다 (저장 없음).
> 이 문서는 그 위에 얹는 기능: 튜터가 버튼 하나로 **이번 회차의 학생별 점수를 스냅샷으로 박제하고
> 마감 처리**한다. 박제된 개인 토탈 점수를 AX2 로 넘긴다.

관련: [assignment-lms-grading.md](assignment-lms-grading.md) · [assignment-lms-ERD.md](assignment-lms-ERD.md)

---

## 1. 큰 그림

```
튜터가 "이번 회차 점수 마감" 클릭
   → 이 회차에 속한 과제 산정
   → grading.compute() 로 학생별 점수 계산
   → RoundScore 테이블에 (회차 × 학생) 스냅샷 저장   ← 여기서 "박제"
   → 결과 표 + CSV(개인 토탈 점수) → AX2 전달
```

- **실시간 계산 로직은 그대로 재사용** — `grading.compute()` 에 "대상 과제" 파라미터만 추가.
- 마감은 **덮어쓰기(재마감) 가능**. 점수가 바뀌었거나 팀이 뒤늦게 편성되면 다시 누른다.
- **저장은 `apps/tutor` 안에서만** — `apps/core` 모델은 건드리지 않는다.

---

## 2. "이번 회차" 과제 스코프

과제(`Assignment`)에는 회차 정보가 없다. 회차는 외부 AX `rounds_evaluationround` 가 기간으로 정의한다
(`evaluation_start_at` ~ `evaluation_end_at`). 그래서 **마감일 기준**으로 회차에 귀속시킨다.

```
회차 R 의 과제 = 직전 회차 종료 < Assignment.due_at ≤ R.evaluation_end_at
                 AND deleted_at IS NULL
```

- 각 회차가 "지난 회차가 끝난 이후 ~ 내 종료일" 사이의 과제를 전부 가져간다.
- **팀 미편성 갭 구간**(회차 종료 후 다음 회차 시작 전)에 만든 과제도 다음에 마감할 회차로 자동 흡수된다.
- 튜터는 마감 확인 화면에서 **포함 과제 목록을 보고 조정**할 수 있다 (제외/추가).
- "직전 회차 종료"는 AX 에서 `evaluation_end_at < R.evaluation_end_at` 인 회차 중 가장 큰 값.
  없으면(첫 회차) 하한 없음.

---

## 3. 집계 & 스냅샷

### 3.1 계산

`grading.compute(student_ids, assignments=<이 회차 과제들>)` 를 호출한다.
계산 규칙(성취도 70% + 성실성 30%, 4영역 재정규화, 최저보장, 지각감점, 미채점 제외, 팀 상속)은
[grading 문서](assignment-lms-grading.md) 그대로. 이 기능은 **대상 과제만 이 회차로 좁힐 뿐**이다.

> `grading.compute()` 는 현재 `Assignment.objects.filter(due_at__lt=now)` 로 마감된 전체 과제를 본다.
> `assignments` 파라미터를 추가해 명시적으로 넘기면 그 목록만 쓴다 (하위호환: None 이면 기존 동작).

### 3.2 저장 — `RoundScore` (테이블 1개)

마감 시 **대상 학생 수만큼 행을 생성/갱신**한다.

| 컬럼 | 예시 | 의미 |
|---|---|---|
| `round_id` | 61 | AX 라운드 id |
| `round_title` | "AX 3차 프로젝트 평가" | 스냅샷 (AX 에서 이름 바뀌어도 유지) |
| `student_id` | 12345 | AX `accounts_user.id` (FK 아님) |
| `student_name` | "김학생" | 스냅샷 |
| `total` | 72.3 | **최종 점수 — AX2 로 넘기는 값** (0~100, 소수 1자리) |
| `achievement` | 69.0 | 성취도 부분 |
| `sincerity` | 80.0 | 성실성(제출률) 부분 |
| `team_included` | `false` | 팀 과제 점수가 반영됐는지 (팀 미편성이면 `false`) |
| `graded_count` | 4 | 채점 완료된 대상 과제 수 |
| `ungraded_count` | 1 | 제출했으나 미채점 → 집계 제외된 수 |
| `total_count` | 5 | 이 회차 대상 과제 수 |
| `breakdown` | `{"individual_required": 45.7, ...}` | 영역별 내역 (JSON, 감사용) |
| `assignment_ids` | `[3, 7, 8, 11, 12]` | 이 스냅샷이 집계한 과제 (재현/검증용) |
| `closed_at` | 2026-09-01 14:00 | 마감/재마감 시각 |
| `closed_by` | 2 | 마감한 튜터 id |
| `policy_snapshot` | `{...}` | 마감 시점 `GradingPolicy` 값 (JSON) |

- **유니크 제약**: `(round_id, student_id)` — 재마감은 이 행을 덮어쓴다.
- `total = None` 가능 (산출 불가 — 채점된 과제 0건 등). CSV 에서는 공란.
- `apps/tutor/models.py` 에 정의. `apps/core` 무관.

---

## 4. 팀 미편성 갭 처리

회차가 끝나고 다음 팀이 편성되기까지 며칠 걸릴 수 있다. 그 사이에도 **개인 점수는 계속 쌓여야** 하고,
팀이 편성되면 팀 점수가 합쳐져야 한다.

`grading.compute()` 는 이미 **팀이 없으면 팀 영역을 빼고 개인 영역만으로 재정규화**한다. 따라서:

| 시점 | 동작 |
|---|---|
| 팀 미편성 상태에서 마감 | 개인 점수만으로 `total` 산출, `team_included = false` 저장 |
| 학생 관리 화면 표시 | "N차 회차 마감됨 · 개인 점수만 (팀 미편성) · 팀 편성 후 재마감 필요" |
| AX 에 팀 편성 데이터 등장 후 튜터가 다시 마감 | 팀 과제까지 포함해 `total` 재계산, `team_included = true` 로 갱신 |
| AX2 전달 | 튜터 판단 (개인만 넘길지, 팀까지 합산 후 넘길지) |

→ **별도 설계 불필요.** 3.2 의 재마감 + `team_included` 플래그로 충분하다.

---

## 5. 마감 흐름

1. **튜터 학생 관리 화면**(`/tutor/students/`) 상단 "이번 회차 점수 마감" 버튼
2. **확인 화면** — 마감 누르기 전에 보여줄 것:
   - 대상 회차 (id · 제목 · 기간 · AX status)
   - 대상 학생 수
   - **포함 과제 목록** (제목 · 마감일 · 개인/팀 · 필수/선택) + 제외/추가 조정
   - **미채점 제출물 N건** — 있으면 굵게 경고 ("집계에서 제외됩니다")
   - 팀 편성 여부 → 미편성이면 "개인 점수만 마감됩니다" 안내
   - 이미 마감된 회차면 "재마감 — 기존 스냅샷을 덮어씁니다"
3. **POST** → `grading.snapshot(round, closed_by, assignments)` → `RoundScore` 저장(덮어쓰기)
4. **결과 화면** — 학생별 최종 점수 표 + CSV 내보내기

---

## 6. 재마감

- 언제든 다시 누를 수 있다. `(round_id, student_id)` 행을 덮어쓰고 `closed_at` 갱신.
- 이력은 남기지 않는다 (필요해지면 `version` 컬럼 추가). AX2 전달 전 최종본만 의미 있음.
- 용도: 마감 후 튜터가 점수 수정 / 팀 뒤늦게 편성 / 미채점분 채점 완료.

---

## 7. 마감 후 동작

**소프트 마감.** 제출·재제출·평가·AI 채점은 계속 동작한다 (운영상 필요). 하드 잠금은 하지 않는다.

### 7.1 학생 — "점수 미반영" 경고

과제가 **이미 마감된 회차 스냅샷에 실제로 집계됐으면**(`RoundScore.assignment_ids` 에 포함):

- `grading.scored_assignment_ids()` → 마감된 모든 회차가 집계한 과제 id 집합.
- `grading.score_locked_close(assignment)` → `assignment.id in` 그 집합 (bool).
- 스코프를 다시 계산하지 않고 **박제된 `assignment_ids` 를 신뢰** → 튜터가 확인 화면에서 제외한 과제는 포함 안 됨(정확), 마감 시각·경계 엣지케이스도 없음.
- 제출 폼([submission_form.html]): "이 과제가 속한 회차는 점수 집계가 마감됐습니다. 지금 제출해도 **회차 점수에는 반영되지 않습니다.** 튜터 피드백은 받을 수 있습니다."
- 과제 목록: 해당 행에 "회차 점수가 마감되어, 지금 제출해도 점수에 반영되지 않습니다" 안내.
- **제출 자체는 막지 않는다.** 학생 기록·GitHub·튜터 피드백엔 남는다.

> gap 과제(마감된 회차 종료 후 ~ 새 회차 시작 전에 생성)는 어느 스냅샷에도 없으니 **잠기지 않는다** — 다음 회차에서 채점된다. 회차 스코프는 항상 `due_at` 기준(§2)이라, 새 회차가 시작되면 그 회차 창에 속한 과제부터 다시 정상 누적된다.

### 7.2 튜터 — "재마감 필요" 배너

점수집계 확인 화면(`round_close`)에서 `_preview` 가 **실시간 `compute` 결과 ↔ 박제된 `RoundScore` 스냅샷**을 비교:

- `stale_count` = total/achievement/sincerity(소수 1자리)가 달라진 학생 수.
- `stale_count > 0` 이면 배너: "마지막 마감 이후 점수가 달라진 학생 N명 — 재마감하면 최신 값이 반영됩니다."
- 마감 후 신규 지각 제출, 마감 후 채점 완료 둘 다 잡힌다.

### 7.3 회차가 넘어간 뒤

`round_close` 는 항상 `accounts.get_current_round()` 대상이라, 다음 회차가 `IN_PROGRESS` 가 되면
지난 회차는 UI 로 재마감할 수 없다. 지난 회차 보정이 필요하면 `manage.py shell` 로 처리
(향후 `round_close/<round_id>/` 경로 고려 — §14).

---

## 8. 데이터 모델 (변경 요약)

```
apps/accounts_client/models.py  (+)  EvaluationRound        managed=False · rounds_evaluationround 읽기 전용
                                     — id, title, status, evaluation_start_at, evaluation_end_at
apps/accounts_client/services.py (+) get_round_period(round_id=None) -> (start, end) | None
                                     get_previous_round_end(round_id) -> datetime | None
apps/tutor/models.py            (+)  RoundScore             (round_id, student_id) 유니크 · §3.2
apps/tutor/grading.py           (~)  compute(student_ids, assignments=None)   ← 파라미터 추가 (하위호환)
                                (+)  snapshot(round, closed_by) -> list[RoundScore]
                                (+)  scored_assignment_ids() / score_locked_close(assignment)  §7.1
apps/tutor/views_round.py       (+)  _preview.stale_count  §7.2
```

**`apps/core` 는 건드리지 않는다.** `Assignment` 에 `round_id` 를 추가하지 않고, 회차 귀속은
마감일 범위(§2)로 계산하며 결과를 `RoundScore.assignment_ids` 에 박제한다.

### 외부 데이터 원칙

`rounds_evaluationround` / `user_round_team_view` / `ax_user_team_login_view` 는 **전부 읽기 전용.**
`managed=False`, `AccountsRouter` 가 write·migrate 차단, 커넥션도 `default_transaction_read_only=on`.
이 기능은 외부 테이블에 **INSERT/UPDATE/DELETE 를 절대 하지 않는다.**

---

## 9. 화면

| 화면 | 내용 |
|---|---|
| 튜터 · 학생 목록 상단 | "이번 회차 점수 마감" 버튼 + (마감됨이면) 배지 |
| 마감 확인 화면 | §5.2 — 대상/과제/미채점/팀여부, 조정 후 실행 |
| 마감 결과 화면 | 학생별 `total`/`achievement`/`sincerity`/`team_included`/미채점, CSV 내보내기 |
| 학생 상세 | "N차 회차 마감됨" 배지 (해당 회차 스냅샷 있으면) |

등급·석차는 만들지 않는다.

---

## 10. CSV 내보내기 (AX2 전달용)

마감 결과 화면에서 다운로드. **개인 토탈 점수**를 AX2 로 넘긴다 (AX2 가 나중에 자기 시스템에서 합산).

| 컬럼 | 예 |
|---|---|
| `student_id` | 12345 |
| `student_name` | 김학생 |
| `round_id` | 61 |
| `round_title` | AX 3차 프로젝트 평가 |
| `total` | 72.3 |
| `team_included` | false |
| `closed_at` | 2026-09-01T14:00:00+09:00 |

- 인코딩 UTF-8 (BOM) — Excel 한글 깨짐 방지.
- `total` 이 `None` 인 학생은 공란.

---

## 11. 권한

- 마감 실행 / 결과 조회 — **튜터만** (`accounts.is_tutor`). 학생 비노출.
- admin 에서 `RoundScore` 조회 가능(읽기), 수정은 재마감으로만.

---

## 12. 결정 요약 (rationale)

| 결정 | 이유 |
|---|---|
| 스냅샷 테이블 1개 (`RoundScore`) | 회차 메타는 행마다 중복돼도 24행 규모라 무해. 조인 없이 단순 |
| `apps/core` 안 건드림 | `Assignment.round_id` 추가는 공통 담당 영역 + 마이그레이션. 마감일 범위로 계산 가능하므로 불필요 |
| 회차 스코프 = 마감일 범위 | AX 가 회차를 기간으로 정의. 갭 구간 과제도 다음 회차로 자연 흡수 |
| 재마감 = 덮어쓰기 (이력 X) | AX2 전달 전 최종본만 의미. 팀 지연 편성도 재마감으로 해결 |
| 소프트 마감 | 마감 후에도 채점·재제출이 필요한 운영 현실. 하드 잠금은 부작용 큼 |
| `team_included` 플래그 | 팀 미편성 갭에서 "개인만 마감" 상태를 명확히 표시하고 재마감 유도 |
| 외부 데이터 읽기 전용 | AX2 소유 데이터. write 시 데이터 정합성 책임 문제 |
| CSV 로 전달 | AX2 가 우리 DB 직접 읽는 게 아니라, 확정된 개인 토탈만 파일로 넘김 |

---

## 13. 구현 단계

| 단계 | 내용 | 영역 |
|---|---|---|
| 1 | `EvaluationRound` 읽기 모델 + `get_round_period()` / `get_previous_round_end()` | accounts_client (공통 조율) |
| 2 | `grading.compute(student_ids, assignments=None)` — 스코프 파라미터 (하위호환 유지) | tutor |
| 3 | `RoundScore` 모델 + 마이그레이션 | tutor |
| 4 | `grading.snapshot(round, closed_by)` — 스코프 산정 → compute → `RoundScore` 덮어쓰기 · `team_included` 판정 | tutor |
| 5 | 마감 트리거 뷰 + 확인 화면 (대상/포함과제/미채점/팀여부) | tutor |
| 6 | 마감 결과 화면 + CSV + 학생 관리/상세 "마감됨" 배지 | tutor |
| 7 | 테스트 — 스냅샷 정확성 · 재마감 덮어쓰기 · 팀 미편성→재편성 · 미채점 제외 · 스코프 경계(갭) | tutor |

---

## 14. 열린 질문 / 향후

- **미채점분이 많을 때 마감** — 지금은 튜터 판단. 운영해보고 "미채점 X% 이상이면 마감 버튼 비활성" 같은 가드가 필요할 수 있음.
- **CSV 전달 방식** — 수동 다운로드 → 전달. 자동화(AX2 API push 등)는 범위 밖.
- **회차 롤오버 자동 감지** — 현재 `_current_round_id()` 는 IN_PROGRESS 라운드를 캐시. AX `status` 가 기간 지나도 안 바뀌는 문제는 이 기능 범위 밖 (마감은 튜터가 수동 트리거).
- **등급/석차/영역 리포트** — 만들지 않음.
