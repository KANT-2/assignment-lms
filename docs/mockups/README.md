# 프로토타입 목업 (참고 자료)

2026-08-26 제작된 정적 HTML 목업. **실제 화면 구현의 레이아웃·인터랙션·문구 참고용**이다.

> 이 목업들은 자체 CSS/JS로 만들어졌다. 실제 구현은 **[../DESIGN.md](../DESIGN.md) + [../LAYOUT.md](../LAYOUT.md) (Bootstrap 5.3 기반)** 로 다시 만든다.
> 목업의 CSS 토큰·색·폰트를 그대로 쓰지 말고, 화면 구성과 흐름만 가져올 것.

이 폴더에 실제 파일을 두려면 아래 이름으로 넣는다 (원본 인코딩 UTF-8 유지):

| 파일 | 화면 | 관련 FR | 담당 |
|---|---|---|---|
| `student-dashboard.html` | 학생 대시보드 — 공지 배너, 달력(강의/과제·평가 일정), 오늘 일정, TODO 위젯, 내 팀, 최근 공개 결과 | PRD 7장 | 학생팀 공용 |
| `student-assignment-submission.html` | 학생 — 과제 목록 → 제출 폼(파일 업로드 + .py/.ipynb 미리보기 + 설명) → 제출 확인 → 재제출 → 마감된 과제 결과(AI/튜터 평가) | FR-003·004·005·006·014 | 학생 A(제출/미리보기), 학생 B(재제출/결과) |
| `tutor-assignment-management.html` | 튜터 — 과제 목록 + 등록/수정 모달 + 삭제(undo 토스트) → 제출 현황 명단(검색·상태필터·정렬, 팀 전개) → 제출물 검토(이전/다음 이동, AI 채점 생성, 튜터 점수+피드백) | FR-001·002·007·008·010·011·012·013 | 튜터 A(과제관리/현황), 튜터 B(검토/평가) |

---

## ⚠ 목업 ≠ 실제 명세 — 아래는 목업을 따르지 말 것

목업 제작 후(2026-08-27) 바뀐 결정. **agent에게 "목업대로 구현" 시키면 아래를 잘못 만든다.**

### 1. 최종 점수(`final_score`) — 목업의 "튜터 8 : AI 2" 가중은 폐기

목업 JS:
```js
function computeFinalScore(tutorScore, aiScore) {
  if (aiScore == null) return tutorScore;
  return tutorScore * 0.8 + aiScore * 0.2;   // ← 이 방식 안 씀
}
```
- **실제**: `final_score = Evaluation.score` (튜터 점수 그대로). `apps/core/signals.py` 가 `Evaluation` 저장 시 `Submission.final_score` 로 복사.
- 집계 방식(가중치 등)은 **오픈 퀘스천**. 목업의 "튜터 94점 · AI 90점 반영 (8:2)" 같은 표기 UI는 만들지 말 것.
- 결과 화면엔 AI 평가와 튜터 평가를 **각각** 보여주고, "최종 점수"는 튜터 점수(= `final_score`)만.

### 2. AI 평가 — "1회만, 재생성 불가"(튜터 목업 문구)는 틀림

- **실제**: AI 평가는 **재생성 가능**. 재생성하면 기존 `AiEvaluation` 행을 덮어씀(이력 없음).
- 목업 튜터 화면의 "이 제출물에 대해 1회만 생성되며 재생성할 수 없습니다" 안내 문구·`aiGenBtn.style.display = "none"` 로직은 따르지 말 것. "AI 다시 채점" 버튼은 항상 노출.

### 3. 팀장(대표자) — 없음

- 목업의 팀 제출물 `submittedBy`("김대중"), `(대표)` chip, `.member-chip.rep` 스타일 → **개념 폐기**.
- **실제**: 팀 과제 제출물은 `team_id` 만 저장. 팀원 누구나 팀을 대신해 제출. 제출자 정보 저장 안 함.
- 제출 현황 명단의 팀 행에서 "제출자: 홍길동" 표기 대신 "제출됨/미제출"만.

---

## 그 외 구현 시 주의

- **더미 데이터**: 목업의 학생 이름(김대중, 이순신 …), 팀 구성, 팀원 이메일(messi@…)은 전부 예시. 실제는 `accounts_user` / `teams_team` (외부 AX Evaluator DB) 참조 → `apps/accounts_client/services.py`.
- **코드 미리보기(FR-005)**: 목업은 자체 JS 하이라이터 + 노트북 파서. 실제 구현은 `nbconvert` + `Pygments` (requirements.txt에 포함) 사용.
- **과제 등록 폼**: 목업 모달에 `weight_tier` 입력란 없음 — 맞음. 튜터가 UI에서 설정하지 않는다.
- **상태값**: "평가 대기 중" / "제출 기록 없음" 등은 저장 안 하고 파생 — 계산식은 [../assignment-lms-ERD.md](../assignment-lms-ERD.md) §6.
- **소프트 삭제 undo**: 목업의 "삭제됨 · 실행취소" 토스트 → 실제로는 `Assignment.deleted_at` 채우기 / `restore()` 로 되돌리기 (ERD §5 아님, 모델 참고).

## agent에게 시킬 때 예시

> `docs/mockups/tutor-assignment-management.html` 의 "제출물 검토" 화면을 `DESIGN.md` / `LAYOUT.md` 기준 Bootstrap 5.3 Django 템플릿으로 구현해줘. 단 `docs/mockups/README.md` 의 "목업 ≠ 실제 명세" 3가지는 반영하지 말 것. 데이터는 `apps/core` 모델과 `apps/accounts_client` 헬퍼를 쓴다.
