# assignment-lms

과제 제출·평가 시스템 (Django 6 + PostgreSQL + Django 템플릿)

## 담당 구조

| 영역 | 담당 | 파일 |
|---|---|---|
| config / core 모델 / 공통 템플릿 | 공통 담당 | `config/`, `apps/core/`, `apps/common/`, `apps/accounts_client/` |
| 학생 A — 목록/제출/미리보기 (FR-003·004·005) | 학생팀 | `apps/student/views_submit.py` |
| 학생 B — 재제출/평가결과 (FR-006·014) | 학생팀 | `apps/student/views_result.py` |
| 튜터 A — 과제관리/제출현황 (FR-001·002·007·008·010) | 튜터팀 | `apps/tutor/views_manage.py` |
| 튜터 B — 검토/AI 1차평가/평가 (FR-011·012·013) | 튜터팀 | `apps/tutor/views_review.py`, `apps/tutor/ai_gemini.py` |
| 튜터 B — 회차 마감·점수집계 | 튜터팀 | `apps/tutor/grading.py`, `apps/tutor/views_round.py` |
| GitHub 제출물 동기화 (선택 기능) | 튜터팀 | `apps/github_sync/` |
| Slack 알림 (선택 기능) | 공통 담당 | `apps/notifications/` |

## 문서

| 문서 | 내용 |
|---|---|
| [docs/assignment-lms-PRD.md](docs/assignment-lms-PRD.md) | 요구사항 (FR/BR/AC), v0.3 |
| [docs/assignment-lms-ERD.md](docs/assignment-lms-ERD.md) | 데이터 모델, v6 |
| [docs/DESIGN.md](docs/DESIGN.md) | 디자인 시스템 (색·타이포·컴포넌트, Bootstrap 5.3 기반) |
| [docs/LAYOUT.md](docs/LAYOUT.md) | 전역 레이아웃 (사이드바 + 탑바 + 메인, 반응형 규칙) |
| [docs/mockups/](docs/mockups/README.md) | 프로토타입 목업 HTML + 실제 명세와 다른 부분 정리 |
| [docs/assignment-lms-grading.md](docs/assignment-lms-grading.md) | 점수 산정 로직 (가중치·성실도·필수 미제출 감점) |
| [docs/assignment-lms-round-close.md](docs/assignment-lms-round-close.md) | 회차 마감·점수집계 화면, 재마감·stale 처리 |
| [docs/assignment-lms-round-close-verification.md](docs/assignment-lms-round-close-verification.md) | 회차 마감 시나리오별 검증 기록 |
| [docs/assignment-lms-late-submission.md](docs/assignment-lms-late-submission.md) | 지각 제출 3단계 윈도우 모델 + DB 매핑 |
| [docs/assignment-lms-github-sync.md](docs/assignment-lms-github-sync.md) | GitHub 제출물 자동 동기화 + 튜터 피드백 이슈 설계 |
| [docs/assignment-lms-github-link-eval.md](docs/assignment-lms-github-link-eval.md) | AI 채점의 GitHub 링크 읽기 설계 (blob 링크만 지원) |
| [docs/github-연동-배포가이드.md](docs/github-연동-배포가이드.md) | GitHub 연동 배포 체크리스트 (OAuth App 등록, redirect_uri) |
| [docs/assignment-lms-troubleshooting.md](docs/assignment-lms-troubleshooting.md) | 자주 겪는 로컬 환경 문제 모음 |
| [docs/source-delivery.md](docs/source-delivery.md) | 소스 인도 체크리스트 (커밋·마이그레이션·환경변수·알려진 이슈) |

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

## AI 1차 평가 (선택 기능, Gemini)

튜터가 검토 화면에서 "AI 채점"을 누르면 제출물(파일 + GitHub 단일 파일 링크)을 Gemini 로 채점해
참고용 점수·코멘트를 붙여준다. 공식 점수는 아니고 튜터가 최종 결정.

- `.env` 의 `GEMINI_API_KEY` 가 없으면 비활성 — 버튼 눌러도 실패 메시지만 뜨고 기존 흐름엔 영향 없음.
- `GEMINI_MODEL` (1순위) → `GEMINI_FALLBACK_MODELS` (쉼표 구분, 순서대로 재시도) 로 혼잡·타임아웃에 대응.
- 실패 원인(키 없음/무효, 사용량 한도, 모델명 오류, 전체 혼잡, 응답 해석 실패)을 튜터 화면에 구체적으로 표시.
- GitHub 링크는 **특정 파일 페이지(`.../blob/...`) 링크만** 읽는다 — 레포·폴더 링크는 제출 시점에 차단됨(아래 GitHub 동기화 참고).

## GitHub 제출물 동기화 (선택 기능, `apps/github_sync`)

학생이 과제를 제출하면 학생 **본인 GitHub 저장소**(public, 기본 `lms-assignments`)에 자동 커밋되고,
튜터가 평가를 저장하면 같은 저장소에 **피드백 이슈**가 생성/갱신된다.
`.env` 에 `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` / `GITHUB_TOKEN_ENC_KEY` 세 값이
모두 있어야 활성화되며, 없으면 완전히 no-op (기존 제출 흐름 영향 없음). 자세한 발급 방법은 `.env.example`.

- 학생·튜터 모두 대시보드에서 **GitHub 연결** 1회(같은 콜백 URL 재사용, 세션으로 흐름 구분) → 이후 자동
- 제출 폼에서 GitHub 링크는 **특정 파일 페이지(`.../blob/...`) 링크만 허용** — 레포 루트·`/tree/`·비공개·깨진 링크는 제출 자체가 그 자리에서 거부됨
- 실제 push/이슈 생성은 **백그라운드 스레드**로 처리(요청 응답을 막지 않음). 테스트/CLI 에서 동기 실행하려면 `GITHUB_SYNC_SYNC=True`
- 배포 서버에 재시도 + 마감 최종본 커밋용 배치를 5분 간격으로 등록:
  ```
  */5 * * * * cd /app && /app/.venv/bin/python manage.py github_sync
  ```

## 협업 규칙

- `main`·`develop` 직접 push 금지 → 브랜치 파고 PR (base: `develop`)
- 브랜치 예: `feat/student-a-submit`, `feat/tutor-b-review`, `fix/...`
- `develop` 은 리포지토리 룰셋으로 **승인(review) 1개 필요** — PR 작성자 본인은 자기 PR을 승인할 수 없음
- `apps/core/models.py`(공유 모델) 수정은 공통 담당에게 요청
- `.env` 는 커밋 금지 (`.gitignore` 등록됨). 키가 늘면 `.env.example` 갱신
- 마이그레이션 파일은 커밋에 포함
