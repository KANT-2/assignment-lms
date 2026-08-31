# assignment-lms

과제 제출·평가 시스템 (Django 6 + PostgreSQL + Django 템플릿)

## 담당 구조

| 영역 | 담당 | 파일 |
|---|---|---|
| config / core 모델 / 공통 템플릿 | 공통 담당 | `config/`, `apps/core/`, `apps/common/`, `apps/accounts_client/` |
| 학생 A — 목록/제출/미리보기 (FR-003·004·005) | 학생팀 | `apps/student/views_submit.py` |
| 학생 B — 재제출/평가결과 (FR-006·014) | 학생팀 | `apps/student/views_result.py` |
| 튜터 A — 과제관리/제출현황 (FR-001·002·007·008·010) | 튜터팀 | `apps/tutor/views_manage.py` |
| 튜터 B — 평가 (FR-011·012·013) | 튜터팀 | `apps/tutor/views_review.py` |

## 문서

| 문서 | 내용 |
|---|---|
| [docs/assignment-lms-PRD.md](docs/assignment-lms-PRD.md) | 요구사항 (FR/BR/AC), v0.3 |
| [docs/assignment-lms-ERD.md](docs/assignment-lms-ERD.md) | 데이터 모델, v6 |
| [docs/DESIGN.md](docs/DESIGN.md) | 디자인 시스템 (색·타이포·컴포넌트, Bootstrap 5.3 기반) |
| [docs/LAYOUT.md](docs/LAYOUT.md) | 전역 레이아웃 (사이드바 + 탑바 + 메인, 반응형 규칙) |
| [docs/mockups/](docs/mockups/README.md) | 프로토타입 목업 HTML + 실제 명세와 다른 부분 정리 |

UI 작업 전 DESIGN.md / LAYOUT.md 를 먼저 확인. shell(사이드바·탑바)은 `apps/common/templates/` 에서만 관리하고 각 페이지는 `{% extends "base.html" %}`.

## 처음 세팅 (팀원용)

```powershell
git clone <repo-url>
cd assignment-lms

py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # 배포 서버는 requirements.txt 만

copy .env.example .env      # .env 값을 로컬 환경에 맞게 수정 (특히 DB 비밀번호)

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- 기본 설정 모듈: `config.settings.dev` (manage.py 기본값)
- PostgreSQL DB 2개 필요:
  - `default` — 이 프로젝트 전용 (`DB_*` 환경변수)
  - `accounts` — 외부 계정/팀 DB, 읽기 전용 (`ACCOUNTS_DB_*` 환경변수)

## GitHub 제출물 동기화 (선택 기능, `apps/github_sync`)

학생이 과제를 제출하면 학생 **본인 GitHub 저장소**(public, 기본 `lms-assignments`)에 자동 커밋된다.
`.env` 에 `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` / `GITHUB_TOKEN_ENC_KEY` 세 값이
모두 있어야 활성화되며, 없으면 완전히 no-op (기존 제출 흐름 영향 없음). 자세한 발급 방법은 `.env.example`.

- 학생은 대시보드에서 **GitHub 연결** 1회 → 이후 제출 시 즉시 push 시도
- 배포 서버에 재시도 + 마감 최종본 커밋용 배치를 5분 간격으로 등록:
  ```
  */5 * * * * cd /app && /app/.venv/bin/python manage.py github_sync
  ```

## 협업 규칙

- `main` 직접 push 금지 → 브랜치 파고 PR
- 브랜치 예: `feat/student-a-submit`, `feat/tutor-b-review`
- `apps/core/models.py`(공유 모델) 수정은 공통 담당에게 요청
- `.env` 는 커밋 금지 (`.gitignore` 등록됨). 키가 늘면 `.env.example` 갱신
- 마이그레이션 파일은 커밋에 포함
