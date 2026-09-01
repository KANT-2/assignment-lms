# AI 채점 — 학생 GitHub 링크 코드 읽기 v1

**작성:** 2026-09-01 · **구현 예정:** `apps/tutor/ai_gemini.py` + `apps/tutor/github_fetch.py`
**담당:** 튜터 B · **범위(1단계):** 공개 레포의 **단일 파일(blob) 링크만**, 무인증

> 학생이 과제 제출 시 링크를 추가할 수 있다(`request.POST.getlist("links")` → `SubmissionFile(kind=OTHER, file_url=링크)`).
> 지금은 AI 채점이 링크 내용을 못 읽고 `(텍스트 파일이 아니라 내용 생략)` 으로만 프롬프트에 들어간다.
> 이 문서: GitHub 단일 파일 링크면 그 파일을 받아와 프롬프트에 넣는다.

관련: [assignment-lms-grading.md](assignment-lms-grading.md) · `apps/tutor/ai_gemini.py`

---

## 1. 대상 링크 형태 (1단계)

```
https://github.com/{owner}/{repo}/blob/{ref}/{path...}
https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path...}
```

- `blob` URL → `raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}` 로 변환해 GET
- `raw` URL → 그대로 GET
- **그 외 GitHub URL**(레포 루트, `/tree/`, PR, commit, gist) → **이번엔 처리 안 함.**
  프롬프트에 `(GitHub 링크 — 단일 파일 링크만 지원: {url})` 로 표시
- **GitHub 아닌 링크**(블로그·노션·배포 URL) → 기존대로 `(텍스트 파일이 아니라 내용 생략)`

`?ref=`, `#L10-L20`, 쿼리스트링 등은 파싱 시 무시(경로만 사용).

### 검증 (실측)
```
GET https://raw.githubusercontent.com/jin-park0115/Tutor_task/main/chapter11/task01.py
→ 200, 실제 코드 본문, rate-limit 헤더 없음, 무인증 OK
```

---

## 2. 가져오기 (`apps/tutor/github_fetch.py` 신규)

```
fetch_github_file(url) -> str | None
```

1. `urlparse` → host 가 `github.com` 또는 `raw.githubusercontent.com` 인지 확인
   (아니면 `None` — SSRF 방어: 이 두 도메인만 화이트리스트)
2. `github.com/.../blob/ref/path` → raw URL 로 변환. `raw.githubusercontent.com/...` → 그대로
3. `requests.get(raw_url, timeout=10)`
   - 200 아니면 `None`
   - `Content-Length` / 응답 크기 > 512KB 면 앞부분만 (그래도 아래서 또 자름)
4. `resp.text` 반환. 텍스트 디코드 실패 시 `None`

- 인증 없음. `GITHUB_API_TOKEN` 있으면 헤더에 실어 rate limit 여유 (선택, 없어도 동작)
- `requests` 는 이미 의존성에 있음 (`apps/github_sync/github_api.py` 사용 중)

---

## 3. 프롬프트에 넣기 (`ai_gemini.py` 수정)

`_build_prompt` 의 파일 루프에서, `_read_text(submission_file)` 가 `None` 이고
`file_url` 이 링크일 때:

| 판정 | 프롬프트 |
|---|---|
| GitHub 단일 파일 링크 + fetch 성공 | `[파일: {basename} (GitHub)]\n```\n{내용 (예산 내 절단)}\n```` |
| `.ipynb` 링크 성공 | `_notebook_cells` 로 셀 파싱해서 넣음 |
| GitHub인데 blob/raw 아님 | `[링크: {url}]\n(GitHub 링크 — 단일 파일 링크만 지원)` |
| fetch 실패 (404/타임아웃/비공개) | `[링크: {url}]\n(GitHub 링크 확인 불가)` |
| GitHub 아님 | `[링크: {url}]\n(내용 생략 — 지원하지 않는 링크)` |

- 파일당 상한 `_MAX_CHARS_PER_FILE`(15,000), 전체 `_MAX_CHARS_TOTAL`(40,000) — **기존 예산 그대로** 공유
- 링크가 여러 개면 예산 소진 시까지 처리, 나머지는 `(길이 제한으로 생략)`
- `github_fetch` 는 예외를 올리지 않음 (`None` 반환). 아래 §3.1 이 뒷처리.

### 3.1 링크를 못 읽었을 때 (튜터 뷰 처리)

`ai_gemini.generate()` 가 **읽어낸 자료 수**를 결과에 같이 돌려주고, 뷰(`ai_evaluation_generate`)가 판단한다.

| 상황 | 동작 |
|---|---|
| 읽은 자료 **0건** (링크만 냈는데 접근 실패 등) | **AI 채점 안 함.** `messages.error`: "AI가 GitHub 링크를 읽지 못했습니다: {링크주소}" · `AiEvaluation` 저장 안 함 |
| **일부만** 못 읽음 (파일 + 깨진 링크) | 읽은 걸로 채점. `messages.warning`: "읽지 못한 링크: {주소1}, {주소2}. AI 평가는 나머지 자료 기준입니다." |
| 전부 읽음 | 조용히 진행 (기존과 동일) |

- 메시지에 **링크 주소 원문** 포함 → 튜터가 클릭해 직접 확인
- **Slack 알림은 나중** — 외부 팀 공통 모듈 대기. 지금은 튜터 뷰 메시지만.
- "0건 → 차단" 은 기존 패턴과 동일 (Gemini 실패 시 에러 + 저장 안 함)

구현:
- `_build_prompt` 가 `(prompt, read_count, unreadable_links)` 반환
- `read_count == 0` → `ai_gemini.generate()` 가 **Gemini 호출 전에** `NoReadableContent(unreadable_links)` 예외
- 아니면 `AiResult(score, comment, unreadable_links=[...])` 반환
- 뷰: `except NoReadableContent` → error(+링크주소) / `result.unreadable_links` 있으면 warning 후 저장

---

## 4. 성능

- 링크 1개당 GET 1회, timeout 10초. 보통 <1초.
- AI 채점이 동기라 링크 있으면 그만큼 느려짐 (지금 5~15초 → +1~2초/링크). 허용 범위.
- raw.githubusercontent.com 은 API rate limit(60/5000)에 안 걸림.

---

## 5. 범위 밖 (다음 단계 후보)

- 레포 루트 / 디렉토리 링크 → 트리 walk + 코드 파일 필터 + 다중 fetch
- 비공개 레포 (학생 OAuth 토큰 필요)
- gist, PR diff, 특정 commit
- 링크 유효성 사전 검증 (제출 시점에 "이 링크 못 읽어요" 안내)

---

## 6. 구현 단계

| 단계 | 내용 |
|---|---|
| 1 | `apps/tutor/github_fetch.py` — `fetch_github_file(url)` + URL 파싱/화이트리스트 |
| 2 | `ai_gemini._build_prompt` — 링크 분기 추가 (표 §3) |
| 3 | `.env.example` 에 `GITHUB_API_TOKEN=` (선택, 주석으로 "없어도 됨") |
| 4 | 테스트 — blob→raw 변환, 화이트리스트(비-github 거부), 404 처리, .ipynb, 예산 절단, 비-blob github URL |

`apps/core` · 외부 DB 무관. `apps/github_sync` 와도 독립 (그건 push 전용).
