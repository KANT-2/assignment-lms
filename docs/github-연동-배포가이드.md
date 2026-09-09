# GitHub 연동 배포 가이드 (배포 담당자용)

LMS의 GitHub 연동 두 기능을 켜기 위한 설정. **도메인이 정해진 뒤 한 번만** 하면 된다.

- **학생 제출물 자동 백업**: 학생이 과제를 제출하면 학생 본인 GitHub 공개 저장소(`lms-assignments`)에 자동 커밋
- **튜터 피드백 이슈**: 튜터가 평가를 저장하면 그 저장소에 피드백이 이슈로 남음

설정 안 하면(아래 `.env` 값이 비어 있으면) 이 두 기능만 꺼지고 LMS 나머지는 정상 동작한다.

---

## 1. GitHub OAuth App 등록

GitHub에서 (개인 계정 또는 조직 계정):
**Settings → Developer settings → OAuth Apps → New OAuth App**

| 항목 | 값 |
|---|---|
| Application name | 아무거나 (예: `AX LMS`) |
| Homepage URL | 서비스 도메인 (예: `https://lms.example.com`) |
| **Authorization callback URL** | **`https://lms.example.com/github/callback/`** ← 끝 슬래시 포함, 도메인만 실제 값으로 |

등록하면 **Client ID**가 나오고, **Generate a new client secret** 눌러 **Client Secret**을 받는다. (secret은 그 화면에서만 보이니 바로 복사)

> OAuth App은 콜백 URL을 **1개만** 등록할 수 있다. staging 도메인이 따로 있으면 OAuth App을 하나 더 만들어야 한다.
> 권한 스코프(`public_repo`)는 코드가 요청하므로 여기서 설정할 것 없음.

---

## 2. 토큰 암호화 키 생성

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

출력된 문자열 한 줄을 아래 `GITHUB_TOKEN_ENC_KEY`에 넣는다. **분실하면 저장된 GitHub 토큰을 모두 다시 연결해야 하므로** 안전하게 보관.

---

## 3. `.env` 설정

```ini
GITHUB_OAUTH_CLIENT_ID=<1번의 Client ID>
GITHUB_OAUTH_CLIENT_SECRET=<1번의 Client Secret>
GITHUB_TOKEN_ENC_KEY=<2번에서 생성한 키>
GITHUB_OAUTH_REDIRECT_URI=https://lms.example.com/github/callback/
GITHUB_SUBMISSION_REPO_NAME=lms-assignments
```

- **`GITHUB_OAUTH_REDIRECT_URI`** 는 1번의 Authorization callback URL과 **글자 하나까지 똑같이**. 리버스 프록시(nginx 등) 뒤에서 호스트/프로토콜이 틀어지는 문제를 막아준다.
- `GITHUB_SUBMISSION_REPO_NAME` 은 기본값 그대로 두면 됨.
- (선택) `GITHUB_API_TOKEN` — AI 채점이 GitHub 링크를 읽을 때 rate limit 상향용. 없어도 동작. scope 전부 빈 classic token.

---

## 4. 마이그레이션

```bash
python manage.py migrate
```

---

## 5. 재시도 배치 등록 (cron / systemd timer)

5분마다 실행 — 순간 실패한 push·피드백 이슈 재시도 + 마감 시점 최종 커밋:

```cron
*/5 * * * * cd /path/to/app && /path/to/venv/bin/python manage.py github_sync
```

---

## 6. 동작 확인

1. 서버 재시작
2. **학생 계정**으로 로그인 → 대시보드 "🐙 GitHub 백업" 카드 → "GitHub 연결하기" → GitHub에서 "Authorize" → 대시보드로 돌아오면 OK
   - 여기서 `redirect_uri is not associated` 오류가 나면 → 1번 콜백 URL과 3번 `GITHUB_OAUTH_REDIRECT_URI`, 실제 접속 도메인이 서로 다른 것. 셋을 일치시킬 것.
3. **튜터 계정**으로 로그인 → 튜터 대시보드 하단 "🐙 GitHub 연결" 카드 → "GitHub 연결하기" (튜터도 같은 콜백 URL 사용)
4. 학생이 과제 제출 → 몇 초 뒤 `github.com/<학생>/lms-assignments` 에 파일 커밋 확인
5. 튜터가 그 제출물에 평가 저장 → 같은 저장소 Issues 탭에 피드백 이슈 확인

---

## 요약: 도메인 바뀌면

OAuth App의 Authorization callback URL + `.env`의 `GITHUB_OAUTH_REDIRECT_URI` 두 개만 새 도메인으로 고치고 서버 재시작. 그 외엔 건드릴 것 없음.
