# SOURCE DELIVERY — assignment-lms (2026-09-04)

> [SOURCE-DELIVERY-TEMPLATE.md](SOURCE-DELIVERY-TEMPLATE.md) 양식으로 작성.
> 채울 수 없는 항목(수신 팀, 실제 비밀값 등)은 빈칸으로 둠.

---

## 1. 기본 정보

| 항목 | 내용 |
| --- | --- |
| 전달 팀 | KANT-2 / assignment-lms / 2조 |
| 전달자 | (GitHub: jin-park0115) |
| 전달일 | 2026-09-04 |
| Repository | https://github.com/KANT-2/assignment-lms |
| Branch | `develop` |
| 기준 Commit SHA | `ee04c8618be129acfbf83d069ea001b80514895d` (`ee04c86` Merge PR #87) |
| 관련 Issue / PR | 최근 통합: #87 #85 #84 #83 #82 #81 #80 #79 |

---

## 2. 전달 범위

### 포함 기능
- [x] **공통 인증**: AX2 `ax_evaluation.accounts_user` 자격증명 로그인, 역할 게이트(TUTOR/STUDENT), `DEV_SKIP_AUTH` 개발 우회
- [x] **튜터 — 강의/차시 관리**: `Lecture` 싱글턴 + `Lesson` 차시, 자료(외부 링크/파일), 강의 영상(YouTube 링크)
- [x] **튜터 — 과제**: CRUD(soft delete/restore), 개인·팀 / 필수·선택 / 중요도, 마감일·지각감점, 첨부파일
- [x] **튜터 — 제출물 대시보드 / 채점**: 과제별 제출 현황, 튜터 점수 입력, 제출물 미리보기(.ipynb/.py/이미지)
- [x] **튜터 — AI 1차 평가 (FR-012)**: Gemini 루브릭 채점, 모델 폴백 체인(5xx 대비)
- [x] **튜터 — 회차 점수 마감**: `RoundScore` 스냅샷 생성(성취도 0.7 + 성실성 0.3, 4버킷 정규화 가중합), 결과 페이지, CSV 내보내기
- [x] **튜터 — 제출 독려**: Slack 웹훅 알림 + 학생 DM(`SlackIdentity` 매핑)
- [x] **학생 — 대시보드 / 강의 목록·상세 / 과제 제출·재제출 / 결과 조회 / Todo**
- [x] **GitHub 제출물 동기화 (apps.github_sync)**: OAuth 연동, 학생 공개 레포 자동 커밋, `manage.py github_sync` 배치

### 제외 기능 / 미완료 기능
- [x] 있음:
  - **배포 인프라 미구성** — `gunicorn` / `whitenoise` 의존성·설정은 있으나 실제 배포 파이프라인/호스트 없음
  - **이메일 알림** — `config.settings.prod` 전용, 미검증
  - **팀 과제 마감일 제약** — 로직은 완성(`AssignmentForm.clean`), AX2 `team_start`/`team_end` **실데이터가 과거값**이라 현재 미적용 (AX2 협의 중)
  - **차시 자료 파일 업로드** — 현재 스텁: 파일명 문자열만 저장, 실제 바이트 업로드 엔드포인트 없음

---

## 3. 실행 환경

| 항목 | 내용 |
| --- | --- |
| OS | Windows 11 (개발), Linux 배포 가정 |
| Python 버전 | 3.14.6 |
| Django 버전 | 6.1 |
| DBMS | PostgreSQL |
| DB 버전 | 로컬 개발 16.x 기준 (운영 버전 별도 확인 필요) |
| 기타 주요 라이브러리 | psycopg[binary] 3.3.4 · python-dotenv 1.2.3 · google-genai 2.20.0 · cryptography 50.0.1 · requests 2.34.2 · nbconvert 7.17.1 · Pygments 2.21.0 · Pillow 12.3.0 · django-widget-tweaks 1.5.1 · gunicorn 26.2.0 · whitenoise 6.12.0 (전체: `requirements.txt`) |

> 비밀번호, API Key, Token, Webhook URL 등 민감정보는 문서에 직접 작성하지 않습니다.

---

## 4. 실행 방법

```bash
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt

copy .env.example .env          # 값 채우기 (6장 참고)

python manage.py migrate        # default DB 에만 적용됨 (accounts DB 는 건드리지 않음)
python manage.py runserver
```

추가 실행 조건:
- **DB 2개 필요**: `default` = `assignment_lms` (우리 소유), `accounts` = `ax_evaluation` (AX2 소유, **읽기 전용**). 라우팅은 `config/routers.py::AccountsRouter`.
- AX2 DB 접속 불가 환경에서는 `.env` 에 `DEV_SKIP_AUTH=True` + `DEV_ROLE=TUTOR|STUDENT` 로 가짜 데이터 구동.
- `python manage.py runserver` 는 프로세스 시작 시점에만 `.env` 로드 → `.env` 수정 후 **재시작 필수**.
- `pytest` 는 `.env` 를 로드하지 않음 → DB 환경변수를 셸에 직접 export (`docs/assignment-lms-troubleshooting.md §5`).
- 정적 파일: `python manage.py collectstatic` (배포 시), whitenoise 서빙.
- GitHub 동기화 배치(선택): cron/systemd 로 5분마다 `python manage.py github_sync`.

---

## 5. DB / Migration 정보

- [x] 신규 Migration 있음

### 적용이 필요한 Migration
- `apps/core`: `0001` ~ `0008_assignmentfile`
- `apps/tutor`: `0001_initial`, `0002_roundscore`
- `apps/github_sync`: `0001_initial`
- `apps/accounts_client`: **마이그레이션 없음** (`managed=False`, AX2 VIEW/테이블 읽기 전용 매핑) — `AccountsRouter` 가 `accounts` DB 로의 마이그레이션을 거부함

### 주요 변경 테이블 / 모델
| 테이블 또는 모델 | 변경 내용 | 비고 |
| --- | --- | --- |
| `assignment_file` (`core.AssignmentFile`) | 신규 — 과제 첨부파일 (`core.0008`) | FK Assignment CASCADE, `related_name="attachments"` |
| `tutor_roundscore` (`tutor.RoundScore`) | 신규 — 회차별 학생 점수 스냅샷 (`tutor.0002`) | `update_or_create` on `(round_id, student_id)` |
| `core.Assignment` | `late_penalty` 추가 (`core.0006`), `Todo.due_date` (`core.0005`) | |
| `core.Lesson` | `blog_link` / `video_url` 제거, 자료/영상 구조 개편 (`core.0007`) | |
| `core.Lecture` | 다중 행 → 단일 행 통합 (`core.0004_consolidate_lectures`) | 앱 규칙상 항상 1행 |

### 기존 데이터 영향 여부
- [x] 영향 없음 — 우리 소유(`assignment_lms`) 테이블만 변경. AX2 공통 데이터(User/Student/Team)는 **읽기만** 하며 스키마·행을 건드리지 않음.
- 참고: 로컬 테스트 데이터 초기화용 `python manage.py reset_domain_data --yes` 제공 (default DB 도메인 테이블만 비움, accounts DB·미디어·auth.User·스키마 미영향).

---

## 6. 환경변수 / 외부 연동

필요한 환경변수 이름만 작성합니다. 실제 값은 별도 안전한 방식으로 공유합니다.

```env
# Django
DJANGO_SETTINGS_MODULE=config.settings.dev        # 배포: config.settings.prod
DJANGO_SECRET_KEY=***
DJANGO_DEBUG=
DJANGO_ALLOWED_HOSTS=

# 이 프로젝트 전용 PostgreSQL
DB_NAME=assignment_lms
DB_USER=
DB_PASSWORD=***
DB_HOST=
DB_PORT=

# AX2 통합 플랫폼 DB (읽기 전용)
ACCOUNTS_DB_NAME=ax_evaluation
ACCOUNTS_DB_USER=
ACCOUNTS_DB_PASSWORD=***
ACCOUNTS_DB_HOST=
ACCOUNTS_DB_PORT=
# AX_ROUND_ID=61          # 비우면 IN_PROGRESS 라운드 자동

# 개발 폴백
DEV_SKIP_AUTH=False
DEV_ROLE=TUTOR

MEDIA_ROOT=media

# AI 1차 평가 (Gemini)
GEMINI_API_KEY=***
GEMINI_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODELS=gemini-flash-latest

# GitHub 제출물 동기화 (3개 모두 있어야 활성, 비우면 no-op)
GITHUB_OAUTH_CLIENT_ID=***
GITHUB_OAUTH_CLIENT_SECRET=***
GITHUB_TOKEN_ENC_KEY=***
GITHUB_SUBMISSION_REPO_NAME=lms-assignments
GITHUB_API_TOKEN=***        # 선택 — AI 채점의 GitHub raw 파일 조회 rate limit 상향

# Slack (apps.notifications.slack)
SLACK_WEBHOOK_URL=***       # 채널 알림
SLACK_BOT_TOKEN=***         # 학생 DM (conversations.open + chat.postMessage)

# prod 전용
# DJANGO_CSRF_TRUSTED_ORIGINS=
# EMAIL_HOST= / EMAIL_PORT= / EMAIL_HOST_USER= / EMAIL_HOST_PASSWORD=
```

외부 연동 정보:
- [x] Slack — 웹훅(채널 독려 알림) + Bot Token(학생 DM). `SlackIdentity` 로 AX user_id ↔ slack_user_id 매핑.
- [x] 외부 API — Google Gemini (`google-genai`), GitHub REST / OAuth (`apps.github_sync`)
- [x] 기타 — AX2 `ax_evaluation` PostgreSQL (로그인·팀·회차 조회, **읽기 전용**)
- [ ] Email — prod 설정에만 존재, 미검증

---

## 7. 주요 URL / 테스트 계정

### 주요 URL
| 기능 | URL |
| --- | --- |
| 로그인 / 로그아웃 | `/accounts/login/` · `/accounts/logout/` |
| 학생 홈(대시보드) | `/` |
| 학생 강의 목록 / 상세 | `/lectures/` 계열 (`name="lecture-list"` / `lecture-detail`) |
| 학생 과제 제출 | `assignment-submit` / `submission-resubmit` |
| 튜터 대시보드 | `/tutor/` (`name="dashboard"`) |
| 튜터 강의 관리 | `/tutor/lecture/` (`name="lecture"`, `lecture-update-api`) |
| 튜터 과제 관리 | `assignment-list` / `assignment-edit` / `assignment-delete` / `assignment-restore` |
| 튜터 제출물 대시보드 / 채점 | `submission-dashboard` / `submission-review` / `submission-ai-eval` |
| 튜터 제출 독려 | `submission-remind` / `submission-remind-all` / `submission-remind-all-assignments` |
| **회차 점수 마감** | `/tutor/round-close/` → `round-close-result` → `round-close-csv` |
| GitHub 연동 | `/github/connect/` · `/github/callback/` · `/github/disconnect/` |
| 관리자 | `/admin/` |

### 테스트 계정
> 실제 운영 비밀번호는 작성하지 않습니다.

| 권한 | ID 또는 계정 구분 | 비고 |
| --- | --- | --- |
| TUTOR | AX2 `ax_evaluation.accounts_user` 중 튜터 역할 계정 | 자격증명은 AX2 소유 — 보안 채널로 별도 전달 |
| STUDENT | AX2 학생 계정 (회차 61 등록자) | 동일 |
| (개발) | `DEV_SKIP_AUTH=True` + `DEV_ROLE` | AX2 DB 없이 가짜 유저로 구동 |

---

## 8. 정상 동작 확인

전달 전에 실제 환경에서 확인한 항목만 체크합니다.

- [x] 서버 정상 실행 (`runserver`, 로컬)
- [x] 로그인 정상 — AX2 `AxUserLogin` 조회 → 역할 게이트 통과, 5개 인증 테스트 통과
- [x] 핵심 기능 정상 — 과제 CRUD, 제출/채점, AI 1차 평가(폴백 포함), 회차 점수 마감
- [x] DB 조회/저장 정상 — default DB 저장, accounts DB 읽기
- [x] Migration 적용 확인 — `migrate` 후 `showmigrations` 전부 `[X]`
- [x] 기존 기능 Regression 확인 — 슬랙 UI 머지 회귀 복구(PR #81), 전체 테스트 스위트 통과
- [x] 주요 화면 오류 없음 — 튜터 대시보드 / 제출물 대시보드 / 회차 마감 결과 페이지

### 검증 결과
- 검증일: 2026-09-04
- 검증자: 튜터 B
- 테스트 결과:
  - 회차 점수 마감 E2E: **[assignment-lms-round-close-verification.md](assignment-lms-round-close-verification.md)** — 25명 스냅샷 = 실시간 `compute` 값 25/25 일치, 스코프 격리·팀 반영·지각 감점·하한 전부 설계대로.
  - 단위 테스트: `apps/tutor/tests/test_round_close.py` · `test_grading*.py` (41개) · `test_ai_gemini.py` · `apps/student/tests/test_submission_views.py` 통과.
  - 로그인: 페이지 200, 리다이렉트, 역할 게이트, AX DB 읽기 확인.

---

## 9. Known Issue / 주의사항

| 구분 | 내용 | 우선순위 | 대응 여부 |
| --- | --- | --- | --- |
| 배포 | 배포 인프라(호스트, WSGI 구동, 정적파일, cron) 미구성 | HIGH | 미대응 |
| 데이터 | AX2 `team_start`/`team_end` 실데이터가 과거값 → 팀 과제 마감일 제약 사실상 미적용 | MEDIUM | AX2 협의 중 (로직은 완성) |
| 기능 | 차시 자료 "내 PC 파일" 업로드는 스텁 — 파일명만 저장, 실제 업로드 엔드포인트 없음 | MEDIUM | 미대응 (계획만) |
| 외부 API | `gemini-3.6/3.7-flash` 간헐 5xx(503/504) | LOW | 대응 — `GEMINI_FALLBACK_MODELS` 폴백 체인 |
| 테스트 | `pytest` 가 `.env` 미로드 → DB 환경변수 수동 export 필요 | LOW | 문서화 (`troubleshooting.md §5`) |
| 운영 | `runserver` 는 시작 시점에만 `.env` 로드 → 수정 후 재시작 필요 | LOW | 문서화 |
| 보안 | AX2 `ax_evaluation` DB 는 연결 레벨 `default_transaction_read_only=on`, 앱에서도 **절대 쓰기 금지** | HIGH | 대응 — `AccountsRouter` + 읽기전용 연결 |

---

## 10. 통합 시 확인 요청 사항

- [x] 기존 공통 User / Student / Team 데이터와 중복 여부 확인 — 우리는 AX2 데이터를 **읽기만** 함. 별도 User 테이블 없음(`accounts_client` 는 `managed=False` 매핑).
- [x] URL / View / Model 이름 충돌 여부 확인 — 앱 prefix: `/admin/`, `/accounts/`, `/github/`, `/tutor/`, 나머지 루트(`apps.core` + `apps.student`). 모델은 `core` / `tutor` / `github_sync` / `accounts_client` 앱 라벨로 분리.
- [x] Migration 충돌 여부 확인 — 우리 앱 마이그레이션은 `core`(8) / `tutor`(2) / `github_sync`(1) 뿐, `accounts` DB 로는 마이그레이션 안 나감.
- [x] 공통 DB Source of Truth 기준 확인 — User/Team/Round/SlackIdentity = **AX2 `ax_evaluation`**. 과제/제출/평가/점수 = 우리 `assignment_lms`.
- [x] 기존 기능 Regression 확인 — 8장 참고.
- [x] 환경변수 누락 여부 확인 — 6장 목록 대조. GitHub 3종은 비우면 no-op, Gemini 비우면 AI 채점만 "생성 실패".

추가 요청:
- AX2 팀에 회차 61의 `team_end` 를 넉넉한 미래 날짜로 세팅 요청 중 (팀 과제 마감 제약 실검증용).
- 배포 담당 확정 시 `config.settings.prod` 환경변수(CSRF/EMAIL/ALLOWED_HOSTS) 채우기.

---

## 11. 전달 완료 체크

- [x] Repository / Branch / Commit SHA 전달 완료
- [x] 실행 방법 전달 완료
- [x] Migration 정보 전달 완료
- [x] 환경변수 목록 전달 완료
- [x] Known Issue 전달 완료
- [x] 전달자 자체 검증 완료
- [ ] 수신자 확인 완료

---

## 최종 전달 요약

**전달 기준 Commit:** `ee04c8618be129acfbf83d069ea001b80514895d` (`develop`)

**현재 상태:** YELLOW
> 기능은 완성·검증됨(회차 점수 마감 E2E 포함). 배포 인프라 미구성, AX2 팀 기간 실데이터 미반영 2건이 남아 GREEN 아님.

**수신 팀이 먼저 확인할 사항:**
1. DB 2개 구성 — `assignment_lms`(쓰기) + `ax_evaluation`(읽기 전용). `config/routers.py` 라우팅 준수, accounts DB 에 절대 쓰기·마이그레이션 금지.
2. 환경변수 — AX2 DB 접속정보 / Gemini / GitHub OAuth / Slack. 없으면 해당 기능만 비활성(로그인은 AX2 DB 필수, 없으면 `DEV_SKIP_AUTH=True`).
3. Known Issue 9장 — 배포 인프라, 팀 과제 마감 제약(실데이터 대기), 차시 파일 업로드 스텁.
