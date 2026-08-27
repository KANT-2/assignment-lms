# 과제 제출 및 피드백 관리 시스템 — ERD

**기준 문서:** PRD v0.3 (2026-08-26)
**작성:** 2026-08-27

---

## 1. 개요

- DB 는 **PostgreSQL 2개**로 나뉜다.
  - **`default`** — 본 프로젝트 전용. 아래 `core` 앱 테이블이 실제로 생성/마이그레이션된다 (`managed=True`).
  - **`accounts`** — 외부 팀 구성 시스템(**AX Evaluator**) 소유. 본 시스템은 **읽기 전용 참조**만 한다 (`managed=False`, 마이그레이션 생성 안 함). → `apps/accounts_client/`
- 두 DB 사이에는 **DB 레벨 FK 를 걸지 않는다.** 외부 사용자·팀은 `id` 값(정수)만 저장하고, 필요 시 `apps/accounts_client/services.py` 헬퍼로 조회한다. (`config/routers.py` 의 `allow_relation` 이 교차 관계를 막음)
- 단일 강의 전용(BR-001)이므로 `LECTURE` 는 사실상 1행이지만, 과제의 소속을 명시하기 위해 테이블로 유지한다.

---

## 2. ERD (Mermaid)

```mermaid
erDiagram
    ACCOUNTS_USER  ||--o{ TEAM_MEMBER   : "소속"
    TEAMS_TEAM     ||--o{ TEAM_MEMBER   : "구성"
    ACCOUNTS_USER  ||--o{ LECTURE       : "담당(튜터)"

    LECTURE        ||--o{ ASSIGNMENT    : "포함"
    ASSIGNMENT     ||--o{ SUBMISSION    : "제출 대상"
    ACCOUNTS_USER  ||--o{ SUBMISSION    : "제출(학생/팀대표)"
    TEAMS_TEAM     ||--o{ SUBMISSION    : "팀 제출"
    SUBMISSION     ||--o{ SUBMISSION_FILE : "첨부파일"
    SUBMISSION     ||--o| AI_EVALUATION : "AI 1차 평가"
    SUBMISSION     ||--o| EVALUATION    : "튜터 평가"
    ACCOUNTS_USER  ||--o{ EVALUATION    : "평가자(튜터)"

    ACCOUNTS_USER {
        bigint  id PK
        string  email
        string  name
        string  role         "STUDENT | TUTOR"
        boolean is_active
        datetime date_joined
    }

    TEAMS_TEAM {
        bigint  id PK
        string  name
    }

    TEAM_MEMBER {
        bigint  id PK
        bigint  team_id FK
        bigint  user_id FK
        boolean is_representative "팀 대표 여부 (AX Evaluator에 필드 추가 요청중 — 9장)"
    }

    LECTURE {
        bigint  id PK
        string  title
        bigint  tutor_id      "accounts_user.id (논리적 참조)"
        datetime created_at
    }

    ASSIGNMENT {
        bigint   id PK
        bigint   lecture_id FK
        string   title
        text     description
        datetime due_at                 "제출 마감일시 (FR-001)"
        boolean  is_required             "필수(true)/선택(false) 라벨 (FR-008)"
        boolean  allow_late              "지각 제출 허용 여부 (FR-007)"
        string   assignment_type         "INDIVIDUAL | TEAM (FR-009)"
        bigint   created_by              "accounts_user.id — 등록 튜터"
        datetime created_at
        datetime updated_at
        datetime deleted_at              "NULL이면 미삭제. 소프트 삭제로 undo 지원 (FR-002)"
    }

    SUBMISSION {
        bigint   id PK
        bigint   assignment_id FK
        bigint   submitter_id            "accounts_user.id — 개인과제=학생 본인 / 팀과제=팀 대표"
        bigint   team_id                 "teams_team.id — 팀 과제일 때만 (NULL 허용)"
        text     description             "제출 설명 텍스트 (FR-004)"
        boolean  is_late                 "제출 시점 기준 마감 초과 여부. 튜터 화면 '지각' 배지용 (BR-004)"
        datetime submitted_at            "재제출 시 갱신 (덮어쓰기, 이력 미보관 — FR-006)"
        datetime locked_at               "튜터 평가 저장 시각. NULL이 아니면 재제출 잠금 (BR-006)"
    }

    SUBMISSION_FILE {
        bigint   id PK
        bigint   submission_id FK
        string   file                    "저장 경로 (MEDIA_ROOT 기준)"
        string   original_name
        integer  size_bytes
        string   content_type
        string   kind                    "PY | IPYNB | OTHER — 미리보기 분기 (FR-005)"
        datetime uploaded_at
    }

    AI_EVALUATION {
        bigint   id PK
        bigint   submission_id FK        "1:1 — 재생성 시 덮어쓰기 (FR-012)"
        integer  score                   "0~100 (BR-007)"
        text     comment
        boolean  is_simulated            "현재 프로토타입은 항상 true (실제 Gemini 연동은 범위 밖)"
        string   model_name              "실연동 시 사용 모델명 (NULL 허용)"
        integer  regenerated_count       "재생성 횟수"
        datetime generated_at
    }

    EVALUATION {
        bigint   id PK
        bigint   submission_id FK        "1:1"
        bigint   evaluator_id            "accounts_user.id — 작성 튜터"
        integer  score                   "0~100 (FR-013, BR-007)"
        text     feedback
        datetime created_at              "최초 저장 = 제출물 잠금 시점"
        datetime updated_at              "저장 후에도 수정 가능 (FR-013)"
    }
```

> `TEAM_MEMBER` 의 실제 테이블명/구조는 AX Evaluator 스키마에 따름. 위는 참조에 필요한 최소 형태의 예시다.

---

## 3. 엔티티 설명

### 3.1 외부 참조 (`accounts` DB · `managed=False`)

| 엔티티 | 설명 | 관련 |
|---|---|---|
| `ACCOUNTS_USER` | 학생·튜터 계정. 역할은 `STUDENT` / `TUTOR` 둘 뿐 (조교 없음) | BR-001, 1.2절 |
| `TEAMS_TEAM` | 팀. 팀 명단은 AX Evaluator 가 관리, 본 시스템은 참조만 | 1.2절, FR-009 |
| `TEAM_MEMBER` | 팀-학생 매핑. 팀 대표 지정 방식은 미확정 → `is_representative` 필드 추가 요청 상태 | FR-009, BR-005, 9장 |

### 3.2 본 프로젝트 (`default` DB · `managed=True`, `apps/core/`)

| 엔티티 | 설명 | 관련 FR/BR |
|---|---|---|
| `LECTURE` | 강의(과목). 단일 강의 운영이라 1행 | BR-001 |
| `ASSIGNMENT` | 과제. 마감일·필수/선택·지각허용·개인/팀 속성 보유. 삭제는 `deleted_at` 소프트 삭제로 undo 지원 | FR-001, FR-002, FR-007~009 |
| `SUBMISSION` | 제출물. `(assignment, 제출단위)` 당 **1행** — 재제출은 덮어쓰기이고 이력을 남기지 않음 | FR-004, FR-006, BR-004, BR-006 |
| `SUBMISSION_FILE` | 제출 첨부파일(복수 가능). `kind` 로 미리보기 방식 결정(.py/.ipynb 렌더링, 그 외 파일명·크기만) | FR-004, FR-005 |
| `AI_EVALUATION` | AI 1차 평가(점수+코멘트). 제출물당 1행, 재생성 시 갱신. 현재는 시뮬레이션 | FR-012, BR-007~009 |
| `EVALUATION` | 튜터의 공식 평가(점수+피드백). 최초 저장 시 제출물 잠금, 이후 수정 가능 | FR-013, BR-006~008 |

---

## 4. 주요 제약 / 규칙

- **제출 유일성**
  - 개인 과제: `UNIQUE(assignment_id, submitter_id)`
  - 팀 과제: `UNIQUE(assignment_id, team_id)`
  - (Django 에서는 조건부 `UniqueConstraint` 2개로 구현)
- **재제출 가능 조건** (BR-006): `now < assignment.due_at` **AND** `submission.locked_at IS NULL`.
  단, 지각 허용 과제는 마감 후에도 *최초 제출*은 가능(FR-007, AC-003) — 재제출만 마감으로 막힘.
- **팀 과제** (BR-005): `submitter_id` 는 팀 대표. 평가(AI/튜터)는 해당 `SUBMISSION` 1건에만 붙고 팀 전원에게 동일 적용.
- **지각 배지** (BR-004): `is_late` 는 학생 화면엔 안 보이고 튜터 화면에서만 "지각 제출" 배지로 노출.
- **점수 범위** (BR-007): `AI_EVALUATION.score`, `EVALUATION.score` 모두 `0 ≤ score ≤ 100` (CHECK 제약).

---

## 5. 저장하지 않고 파생하는 값

| 화면 표시 | 계산 방법 |
|---|---|
| 학생별 과제 상태 (미제출 / 제출완료 / 평가완료) | `SUBMISSION` 존재 여부 + `EVALUATION` 존재 여부 (FR-003) |
| "평가 대기 중" | 마감됨 + `SUBMISSION` 있음 + `EVALUATION` 없음 (AC-005) |
| "제출 기록 없음" | 마감됨 + `SUBMISSION` 없음 (FR-014, AC-002) |
| 제출률 / 미제출자 명단 | 대상 학생·팀 목록(AX Evaluator) − 제출자 (FR-010) |
| 재제출 가능 여부 | 위 BR-006 조건식 |
| 제출물 이전/다음 이동 | 목록 정렬 순서 기준 인접 `SUBMISSION` (FR-011) |

---

## 6. 스키마에 영향 주는 열린 질문 (PRD 9장)

- **인증 방식 미정** → `ACCOUNTS_USER` 를 Django 인증 사용자로 쓸지, 별도 세션 매핑 테이블을 둘지 결정 필요.
- **과제 삭제 시 제출물·평가 처리** → 현재는 `ASSIGNMENT.deleted_at` 소프트 삭제만. 하위 `SUBMISSION`/`EVALUATION` 을 같이 숨길지 물리 삭제할지 정책 필요.
- **팀 대표 지정 방식** → `TEAM_MEMBER.is_representative` 필드 승인 여부에 따라 제출 시 대표 검증 로직 변경.
- **AI 평가 자동 실행 / 공개 시점 분리** → 필요 시 `AI_EVALUATION` 에 `published_at` 등 상태 필드 추가.
- **온라인 강의(FR-015/016)** → 계획 단계. 확정 시 `LECTURE_VIDEO`(영상), `VIDEO_VIEW`(시청 기록) 등 별도 엔티티 추가 예정. 본 ERD 범위 밖.
