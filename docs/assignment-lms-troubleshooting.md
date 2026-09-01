# 트러블슈팅

이 프로젝트에서 실제로 겪은 문제 + 해결. 증상으로 찾으세요.

> 대전제: `git pull` / develop 머지 후에는 **`python manage.py migrate` 필수**,
> 그리고 브라우저 **하드 리프레시**(`Ctrl+Shift+R`).

---

## 1. 화면이 깨져 보임 / 스타일이 안 먹음 / 아이콘이 빈 네모

**증상**
- 햄버거 메뉴(☰)가 빈 네모로만 뜸
- 방금 머지한 CSS 변경이 화면에 반영 안 됨
- 버튼·레이아웃이 예전 모양

**원인**
`runserver`(DEBUG)는 정적 파일에 캐시버스팅 해시를 안 붙인다. 템플릿(`.html`)은
새로 받았는데 브라우저가 **옛 `app.css` 를 캐시**하고 있으면, 새 마크업 + 옛 스타일이
섞여서 깨진다. (햄버거 케이스: `topbar.html` 은 버튼을 그리는데 옛 `app.css` 엔
`.sidebar-toggle` 규칙이 없어서 안 숨겨지고, 안의 SVG는 `stroke` 없는 열린 path라 안 보임)

**해결**
1. **하드 리프레시** — `Ctrl+Shift+R` (`Ctrl+F5`)
2. 그래도면 DevTools(F12) → Network 탭 → **Disable cache** 체크하고 새로고침
3. 그래도면 브라우저 캐시 비우기 / 시크릿 창

**확인 팁**: `apps/common/static/common/css/app.css` 를 직접 열어 해당 규칙이 있는지 보면
"파일 문제"인지 "캐시 문제"인지 갈린다.

---

## 2. 서버 500 — `column ... does not exist` / `no such column`

**증상**
```
django.db.utils.ProgrammingError: column "submission.last_editor_id" does not exist
```

**원인**
누가 모델 필드를 추가하고 마이그레이션을 커밋했는데, 내 로컬에서 `migrate` 를 안 돌림.

**해결**
```bash
python manage.py migrate
```

**예방**: `git pull` 또는 `git merge develop` 직후에는 **항상** `migrate` 한 번.
`makemigrations --check --dry-run` 으로 "누락된 마이그레이션 없음" 도 확인 가능.

---

## 3. 마이그레이션 관련

**`makemigrations` 했더니 이상한 마이그레이션이 생김**
→ 남의 모델 변경을 아직 안 받은 상태에서 돌렸을 수 있음. `git pull` → `migrate` 먼저.

**`migrate` 하면 외부 DB(`ax_evaluation`)도 건드리나?**
→ 아니오. `config/routers.py` 의 `AccountsRouter.allow_migrate` 가 `accounts` DB /
`accounts_client` 앱에 대해 `False` 를 반환해서 차단한다. `migrate --plan` 출력에는
관련 줄이 보일 수 있지만 **실행은 안 됨**.

**충돌 없는 마이그레이션 번호 관리**
→ 같은 앱에서 두 명이 동시에 `000X_*` 를 만들면 머지 시 꼬인다. 새 마이그레이션
만들기 전에 develop 최신화하고, PR은 빨리 머지.

---

## 4. 로그인 / 권한 (403, 튜터·학생 라우팅)

**튜터로 로그인하면 403, 서버 껐다 켜도 403**
과거 원인: `apps/student/urls.py` 에 `path("")` 가 두 개라 `@student_required` 뷰가
역할 라우터를 가려서 튜터가 막혔다. → URL 패턴 순서/중복 확인.

**"미승인 계정" 으로 로그인 거부됨**
→ `ax_evaluation.accounts_user` 에서 `is_active=True AND approval_status='approved'`
여야 로그인 허용. AX2 쪽에서 승인 안 된 계정.

**로컬에서 로그인 없이 화면 보고 싶음**
→ `.env` 에 `DEV_SKIP_AUTH=True`. 그러면 고정 dev 유저로 자동 로그인 +
`apps/accounts_client/services` 가 가짜 데이터 반환 (AX DB 없이 동작).
**평소엔 `False`** (실제 계정 로그인). prod 에서는 절대 켜지 말 것.

**`dev` 유저 IntegrityError (`auth_user_username_key`)**
→ 예전 `dev` 유저(id=1)와 새 `dev`(id=999999) 충돌. 미들웨어가 스테일 행을
지우게 돼 있지만, 남아 있으면 로컬 DB에서 `username='dev'` 행 수동 삭제.

---

## 5. git / 브랜치 / 머지

**"stale 머지" — 팀원은 404 나는데 나는 됨**
→ 로컬 `develop` 이 오래됨. `git merge develop` 말고:
```bash
git fetch origin
git merge origin/develop      # ← origin/ 을 붙인다
```

**feature 브랜치에 develop 을 pull 해버렸는데 괜찮나?**
→ feature 브랜치에 고유 커밋이 없으면 **fast-forward** 라 안전 (머지 커밋도 안 생김).
고유 커밋이 있으면 머지 커밋이 생기는데 그것도 정상. 충돌만 없으면 OK.
확인:
```bash
git fetch origin
git rev-list --left-right --count origin/develop...HEAD   # (behind  ahead)
git merge-tree --write-tree HEAD origin/develop; echo $?   # 0=clean, 1=conflict
```

**내 PR이 머지됐는데 로컬 브랜치가 뒤처져 보임**
→ 정상. PR 머지 후 로컬 feature 브랜치는 develop보다 뒤처진다. 그 브랜치는
지우고 `feat/tutor_b` 나 새 브랜치를 develop 최신에서 다시 파면 됨.

**`origin/feat/xxx` 가 로컬보다 43커밋 뒤처짐**
→ 원격 브랜치가 stale일 뿐. 그 커밋들이 전부 develop에 있으면 잃은 것 없음.
`git push` 로 동기화하거나 그냥 두면 됨.

**커밋/푸시 전 체크 (팀 규칙)**
→ 브랜치 생성·커밋·푸시 전에 담당자 검토. 다른 브랜치와 충돌 위험 있으면
작업 중단하고 보고.

---

## 6. 테스트 (pytest) 가 DB에 접속 못 함

**증상**
```
django.db.utils.OperationalError: connection ... failed: fe_sendauth: no password supplied
```

**원인**
`pytest` 는 `manage.py` 를 안 거쳐서 **`.env` 를 로드하지 않는다**
(`pyproject.toml` 의 `[tool.pytest.ini_options]` 는 `DJANGO_SETTINGS_MODULE` 만 설정).

**해결** — DB 환경변수를 export 하고 실행 (PowerShell 은 `$env:` 사용):
```bash
export DB_NAME=assignment_lms DB_USER=postgres DB_PASSWORD='...' DB_HOST=127.0.0.1 DB_PORT=5432
export ACCOUNTS_DB_NAME=assignment_lms ACCOUNTS_DB_USER=postgres ACCOUNTS_DB_PASSWORD='...' ACCOUNTS_DB_HOST=127.0.0.1 ACCOUNTS_DB_PORT=5432
export DJANGO_SECRET_KEY=test-key DEV_SKIP_AUTH=False
python -m pytest -q --reuse-db
```
- `ACCOUNTS_DB_*` 도 로컬 postgres 로 돌려서 **원격 AX 서버는 안 건드림** (테스트는
  `databases = {"default"}` 라 실제 사용 안 함, 하지만 test DB 셋업은 시도함).
- `--reuse-db` : 매번 test DB 재생성 안 함 (모델 바꿨으면 `--create-db` 한 번).

**PowerShell 에서 `pytest apps/**/test_*.py` 가 안 됨**
→ PowerShell 은 glob 확장을 안 한다. 디렉터리를 주거나 파일을 나열:
```powershell
python -m pytest apps/tutor/tests/ -q
```

**`No directory at: .../staticfiles/` 경고**
→ 무해. `collectstatic` 안 해서 나는 경고. 테스트엔 영향 없음.

---

## 7. AI 채점 (Gemini)

**`404 NOT_FOUND. This model ... is no longer available`**
→ 모델이 폐기됨. `.env` 의 `GEMINI_MODEL` 을 현재 제공되는 걸로 (`gemini-3.6-flash` 등).
사용 가능 모델 확인:
```python
from google import genai
for m in genai.Client(api_key=KEY).models.list():
    if 'generateContent' in (m.supported_actions or []): print(m.name)
```

**`504 DEADLINE_EXCEEDED` / `503 UNAVAILABLE`**
→ Gemini 쪽 일시적 과부하. 뷰가 잡아서 "AI 채점 서버가 혼잡합니다" 메시지 표시.
잠시 후 "다시 채점" 누르면 대개 됨. (25초 타임아웃)

**AI 채점 눌러도 아무 반응 없음 / 500**
→ `.env` 에 `GEMINI_API_KEY` 없음. 없으면 "AI 평가 생성에 실패했습니다" 메시지.
키는 https://aistudio.google.com/apikey 에서 발급.

**`AFC is not recommended` 경고 (stderr)**
→ google-genai SDK 가 뿜는 무해한 경고. 무시.

---

## 8. 외부 DB (`ax_evaluation` / AX2)

**팀원도 외부 DB를 봐야 하나?**
→ `.env` 의 `ACCOUNTS_DB_*` 를 보안 채널로 받은 실제 값으로 채우면 자동 연결.
`DEV_SKIP_AUTH=True` 면 이 DB 없이도 가짜 데이터로 동작.

**외부 DB에 write 하면 안 됨**
→ 3중 차단: `managed=False` 모델 · `AccountsRouter` · 커넥션 옵션
`default_transaction_read_only=on`. 코드에서도 절대 INSERT/UPDATE/DELETE 금지.

**`Invalid HTTP_HOST header: 'testserver'`**
→ 스크립트에서 `Client()` 쓸 때. `ALLOWED_HOSTS` 에 `testserver` 추가하거나
`settings.ALLOWED_HOSTS = ['*']` 로 오버라이드 (스크립트 한정).

**라운드가 바뀌었는데 화면에 반영 안 됨**
→ `apps/accounts_client/services._current_round_id()` 가 `@lru_cache`. **서버 재시작** 필요.

---

## 9. 템플릿

**`'block' tag ... appears more than once` / `'static' takes at least one argument`**
→ 여러 줄 `{# ... #}` 주석 안에 `{% block %}` / `{% static %}` 를 넣었을 때.
Django 렉서는 여러 줄 `{# #}` 를 인식 못 해서 안의 태그가 파싱된다.
→ `{% comment %}...{% endcomment %}` 또는 한 줄 `{# #}` 사용.

**`{{ csrf_token|json_script:... }}` → `TypeError: first argument must be a string`**
→ `csrf_token` 은 `SimpleLazyObject`. `{{ csrf_token|stringformat:"s"|json_script:"..." }}`
로 문자열 선변환.

**IDE(VS Code)가 `<script>` 안 `{{ ... }}` 에 빨간 줄 ("Property assignment expected")**
→ VS Code JS 파서가 Django 태그를 JS로 읽으려는 오탐. 런타임엔 문제 없음.
JS를 별도 `.js` 파일로 빼면 사라진다 (`json_script` 로 데이터 전달).

---

## 빠른 체크리스트 (뭔가 이상할 때 순서대로)

1. `git fetch origin && git merge origin/develop` (또는 pull)
2. `python manage.py migrate`
3. 브라우저 `Ctrl+Shift+R`
4. `python manage.py check`
5. `runserver` 재시작 (라운드 캐시 / 코드 변경)
6. `.env` 확인 (`DEV_SKIP_AUTH`, `GEMINI_API_KEY`, DB 값)
