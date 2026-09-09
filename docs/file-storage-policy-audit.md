# 3조 LMS 파일스토리지 사용 현황

확인일: 2026-09-09. 기준: 로컬 저장소 HEAD `e8f21d6` 및 현재 작업 트리. 조사 전에 `apps/student/templates/student/lecture.html`에 미커밋 변경이 있었으며 수정하지 않았다. 앱 코드·설정·모델·라우팅·화면과 설치된 Django 6.1 소스를 정적으로 확인했다. 운영 서버·실제 DB·프록시·백업 설정은 확인하지 않았고 런타임 테스트는 실행하지 않았다.

과제 제출물 외에 **과제 첨부 자료(명세서·템플릿·샘플·데이터셋)**가 서버 파일스토리지를 사용한다. **업로드 수신 임시파일**도 생성될 수 있다. 강의 교안 파일 업로드는 UI만 있고 실제 바이트 저장이 연결되지 않았다. CSV Export와 Preview는 디스크에 결과 파일을 저장하지 않는다.

## 항목별 현황

`없음`은 현재 저장소에서 구현을 찾지 못했다는 뜻이며 외부 서비스까지 없다는 뜻은 아니다. `미명시`는 공용 정책 결정 또는 운영 확인이 필요하다는 뜻이다. 크기 표기는 코드의 바이트 수를 기준으로 MiB를 사용했다.

| 항목 | 업로드 / 서버 저장 | 다운로드 | 파일 종류 | 최대크기 | 보관기간·삭제 | 권한 | DB 연결 키 |
|---|---|---|---|---|---|---|---|
| 과제 제출물 | 있음, 복수 파일 및 외부 링크 | 학생용 인증 다운로드 있음. 튜터는 Preview와 이미지/PDF inline 제공, 범용 다운로드 API/UI 없음 | 서버 확장자·MIME 허용목록 없음. ZIP/PDF/DOCX/PPTX/이미지/PY/IPYNB 등 크기 조건 내 수용 | 파일당 31,457,280B = 30MiB | 기간 미명시. 재제출 커밋 후 이전 파일 삭제. 과제 소프트 삭제 시 파일 유지 | 로그인 학생: 본인 개인 제출 또는 소속 팀 제출. 팀원 누구나 제출·재제출 가능. 튜터 Preview는 튜터 역할 검사 | `submission_file.id`, `submission_file.submission_id → submission.id`, `file_url`; `submission.assignment_id → assignment.id`, `student_id` 또는 `team_id` |
| 강의자료/교안 | **실제 파일 업로드 미구현**. 선택한 파일명/URL 메타데이터만 저장 | 저장된 URL 링크 열기. 신규 선택 파일의 다운로드는 보장되지 않음. 전용 파일 제공 API 없음 | FILE/LINK 구분만 존재. 확장자 제한 없음 | 미명시; 실제 파일 미수신 | 파일 보관 해당 없음. 자료 DB 행은 저장 시 삭제 후 재생성, 강의 삭제 시 CASCADE | 등록·수정은 튜터. 학생 강의 조회 뷰에 로그인/역할 검사 없음. 외부 파일은 제공처 권한 | `lesson_material.id`, `lesson_id → lesson.id → lecture_id`; `kind`, `file_url`, `link_url` |
| 공지/게시글 첨부 | 없음. 공지는 정적 배너 문구 | 없음 | 해당 없음 | 해당 없음 | 해당 없음 | 첨부 권한 해당 없음 | 공지/게시판/첨부 모델 없음 |
| 과제 템플릿/샘플파일 | **있음**. 과제 첨부 자료 기능 사용. 복수 파일/외부 링크 | 있음, 공통 인증 다운로드 | 명세서·스타터코드·데이터셋 등. 서버 확장자·MIME 제한 없음 | 파일당 52,428,800B = 50MiB. 초과 파일은 건너뛰고 경고 | 기간 미명시. 튜터가 첨부 삭제 시 물리파일 삭제 시도. 과제 소프트 삭제 시 유지 | 업로드·삭제: 튜터. 다운로드: 로그인 학생 또는 튜터. 작성자/수강/과제 삭제 여부 추가 검사 없음 | `assignment_file.id`, `assignment_id → assignment.id`; `kind`, `file_url`, `file_name`, `file_size`, `link_url`, `uploaded_at` |
| 평가 결과 첨부 | 없음. 점수·텍스트 피드백 저장 | 첨부 다운로드 없음. 회차 CSV는 아래 Export 항목 | 첨부 파일 없음 | 해당 없음 | 파일 보관 해당 없음 | 평가 저장: 튜터. 결과 조회: 본인/소속 팀 학생 등 기존 평가 화면 권한 | 파일 키 없음. 평가 데이터는 `evaluation.submission_id`, `ai_evaluation.submission_id → submission.id` |
| 프로젝트 산출물 | 독립 기능 없음. 팀 과제로 제출하면 과제 제출 스토리지 사용 | 팀 과제 제출 파일 다운로드 | ZIP·보고서·소스 등 제출물과 동일 | 팀 과제 이용 시 파일당 30MiB | 과제 제출물과 동일 | 소속 팀원 제출·재제출·다운로드, 튜터 검토 | 과제 제출물 키와 동일, `assignment.is_team`, `submission.team_id`. 독립 프로젝트 파일 키 없음 |
| 프로필/사용자 이미지 | LMS 내부 업로드 없음 | 이미지 파일 다운로드 없음 | 이름 첫 글자를 CSS 아바타로 표시 | 해당 없음 | 해당 없음 | 해당 없음 | 파일 키 없음. 외부 계정 정보 조회만 사용 |
| 강의 영상 | 직접 업로드 없음. 외부 영상 URL 등록 | 외부 플레이어 재생/링크. LMS 영상 파일 다운로드 없음 | YouTube URL 기반 화면; DB는 URL 문자열 | 로컬 파일 크기 해당 없음 | 로컬 파일 보관 해당 없음. URL 행 교체·삭제 | URL 등록: 튜터. 강의 조회 뷰 인증 검사 없음. 재생 권한은 외부 제공처 | `lesson_video.id`, `lesson_id → lesson.id`, `video_url` |
| 다운로드용 생성 파일 | 사용자 업로드 없음. **CSV를 HttpResponse 메모리에 생성**, 서버 파일 저장 없음 | 회차 성적 CSV 있음. XLSX/PDF Export API 없음 | UTF-8 BOM CSV, `round_{round_id}_scores.csv` | 출력 크기 제한 미명시, 조회 행 수에 비례 | 파일 보관 해당 없음. 요청 시 재생성, 원본 점수는 DB 보관 | 로그인 튜터 | 파일 키 없음. `round_score.round_id`로 조회, `(round_id, student_id)` 유일 제약 |
| 임시파일 | Preview·압축해제·변환용 디스크 파일 없음. **Django 업로드 수신 중 임시파일 생성 가능** | 임시파일 다운로드 API 없음 | 업로드 원본, 임시 이름 `.upload` + 원본 확장자 | 앱 업로드 30/50MiB 검사는 수신 후 실행. 임시파일 자체 상한 미명시 | 정상 요청 종료·업로드 중단 시 닫기/삭제 처리. 비정상 종료 잔여물 정기 청소 미구현 | 앱 파일 제공 경로 없음; OS/프로세스 파일 접근권한 적용 | 임시파일 전용 DB 키 없음. 저장 성공 후 SubmissionFile/AssignmentFile에 연결 |

## 저장 위치와 공용 파일 키

- 운영 설정은 `django.core.files.storage.FileSystemStorage`. 기본 `MEDIA_ROOT`는 저장소 아래 `media`, 환경변수로 변경 가능. S3/공용 파일서비스 연결 구현은 없다.
- 제출물: `submissions/{업로드한 사용자 ID}/{uuid}_{원본파일명}`. 팀 과제도 경로에는 팀 ID가 아닌 업로드 사용자 ID가 들어간다. 팀 접근권한은 경로가 아니라 `submission.team_id`로 판단해야 한다.
- 과제 자료: `assignment_files/{assignment.id}/{uuid}_{원본파일명}`.
- 현재 DB에는 독립적인 공용 `file_id`/`object_key`가 없다. `default_storage.url(saved_name)`을 `file_url`에 저장하고, 읽을 때 `MEDIA_URL` 접두사를 제거해 스토리지 경로를 복원한다. 외부 스토리지 URL로 옮길 경우 이 경로 복원 로직도 변경 대상이다.
- 학생/팀 ID는 외부 계정 DB 값을 보관하는 정수이며 실제 DB FK가 아니다. LMS 내부 `submission_id`, `assignment_id`, `lesson_id`는 FK다.

근거: [저장 설정](../config/settings/base.py#L189), [운영 저장소](../config/settings/prod.py#L30), [제출 저장](../apps/student/views_submit.py#L303), [과제 자료 저장](../apps/tutor/views_manage.py#L111), [URL→경로](../apps/common/preview.py#L50), [모델](../apps/core/models.py#L182).

## 정책 반영 전에 구분할 구현 사항

1. **교안 업로드는 완성된 기능으로 집계하면 안 된다.** JS에서 `matUrl = file.name`만 대입하고 JSON으로 전송한다. API도 `request.body`의 JSON을 읽어 URL 필드만 저장한다. 파일 선택 UI가 있어도 파일 본문은 서버로 가지 않는다. 교안 파일 종류·50MiB 등의 정책을 과제 첨부 기능에서 그대로 가져와 적용했다고 판단할 수 없다.
2. **삭제는 보관기간 정책이 아니다.** 만료일·TTL·주기적 삭제 작업이 없다. 과제 삭제는 `deleted_at`만 채운다. 하드 삭제/DB CASCADE에 대응하는 스토리지 삭제 시그널도 없다. DB만 지우는 관리 명령이나 관리자 삭제는 물리파일을 남길 수 있다.
3. **삭제 실패 복구가 부족하다.** 과제 첨부 삭제는 스토리지 삭제 중 일부 예외를 무시하고 DB 행을 지운다. 재제출은 DB 커밋 후 이전 파일 삭제를 호출하지만 재시도 큐가 없다. 업로드 실패 시 정리 코드가 있어도 프로세스 종료·스토리지 장애까지 정리 완료를 보장하지 않는다.
4. **권한은 현재 API 검사 기준이다.** 과제 자료 다운로드는 로그인+학생/튜터만 검사하고 과제의 `deleted_at`은 검사하지 않는다. 제출 파일 다운로드도 소유자/팀은 검사하지만 과제 소프트 삭제 여부는 검사하지 않는다. 튜터 역할 외 담당 강의/작성자 범위 검사도 없다. 강의 조회 뷰에는 인증 데코레이터가 없다.
5. **개발 MEDIA 직접 제공 경로가 따로 있다.** `DEBUG=True`이면 Django가 MEDIA 경로를 직접 제공하므로 파일 URL을 아는 요청이 업무 API 권한 검사를 거치지 않을 수 있다. 운영 `DEBUG=False`에서는 이 라우트가 없으나, 운영 프록시의 MEDIA 공개 여부는 별도 확인해야 한다.
6. **업로드 크기 정책은 파일당 제한이다.** 앱에서 요청 총 파일 바이트 제한은 명시하지 않는다. 설치된 Django 기본값은 요청당 파일 개수 100개, 메모리 업로드 기준 2,621,440B이다. 메모리 기준은 요청 Content-Length 등을 보고 핸들러를 선택하는 기준이며 2.5MiB 초과 업로드 금지라는 뜻이 아니다. `FILE_UPLOAD_TEMP_DIR=None`으로 OS 임시 디렉터리를 사용한다. 프록시의 요청 제한·타임아웃·임시 스풀 경로·운영 OS 위치는 확인 필요하다.
7. **Preview 지원과 업로드 허용은 별개다.** PY는 하이라이트, IPYNB는 JSON 셀 파싱, CSV/TSV/일반 텍스트는 텍스트 표시, 이미지는 원본 inline, 튜터 PDF는 원본 inline이다. 일반 텍스트 Preview 읽기 상한은 1MiB(+절단 판정 1B)이다. ZIP 압축해제와 DOCX/PPTX/PDF 변환 코드는 없다. `nbconvert` 의존성이 있어도 실제 변환 호출은 없다.

근거: [교안 JS](../apps/tutor/static/tutor/js/lecture_manage.js#L389), [JSON 전송](../apps/tutor/static/tutor/js/lecture_manage.js#L32), [교안 API](../apps/tutor/views_lecture.py#L64), [과제 소프트 삭제](../apps/core/models.py#L167), [재제출 삭제](../apps/student/views_result.py#L174), [첨부 삭제](../apps/tutor/views_manage.py#L74), [첨부 다운로드 권한](../apps/core/views.py#L19), [학생 다운로드 권한](../apps/student/views_submit.py#L389), [튜터 Preview](../apps/tutor/views_review.py#L184), [강의 조회](../apps/student/views_lecture.py#L5), [개발 MEDIA](../config/urls.py#L26), [Preview](../apps/common/preview.py#L33).

프레임워크 임시파일 근거(로컬 설치본): `.venv/Lib/site-packages/django/conf/global_settings.py:311`, `django/core/files/uploadhandler.py:162`, `django/core/files/uploadedfile.py:74`, `django/http/request.py:494`.

## 기타 확인된 파일 관련 처리

- GitHub 동기화가 켜져 있으면 제출 파일을 읽고 외부 GitHub 저장소에 커밋한다. 로컬 임시 복제/압축해제는 없지만 **외부 사본과 커밋 이력**은 로컬 삭제와 별도 보관 대상으로 봐야 한다. 연결 키는 `github_submission_push.submission_id`, `committed_path`, `commit_sha`, 계정의 `repo_full_name`이다. 평가 피드백은 GitHub Issue로 동기화할 수 있으나 로컬 첨부파일 생성은 없다.
- AI 평가용 GitHub 단일 파일 가져오기는 HTTP 응답을 메모리에서 읽는다. 512KiB 초과 응답은 평가 입력에서 제외하지만 응답을 받은 뒤 검사하므로 네트워크 수신량 자체 상한은 아니다. 로컬 저장·압축해제는 없다.
- `output/pdf/assignment_lms_database_erd.pdf`, `tmp/pdfs/`는 저장소 문서 제작 산출물/스크립트다. LMS 요청 처리 Export나 학생 임시파일과 연결되지 않는다. 정적 CSS/JS와 배포용 정적파일 압축도 사용자 업로드 저장소와 별도다.

근거: [GitHub 파일 읽기·동기화](../apps/github_sync/services.py#L206), [GitHub DB](../apps/github_sync/models.py#L61), [AI 외부 파일 읽기](../apps/tutor/github_fetch.py#L20), [CSV 응답 생성](../apps/tutor/views_round.py#L147), [성적 DB](../apps/tutor/models.py#L137), [정적 공지](../apps/student/views_dashboard.py#L35), [이니셜 아바타](../apps/tutor/templates/tutor/student_detail.html#L89), [평가 모델](../apps/core/models.py#L260).

## 4조 전달용 결정 필요 항목

- 현재 공용 저장소 연동 대상: 제출물(팀 과제 산출물 포함), 과제 첨부 자료. 운영 임시영역 정책 대상: 업로드 수신 임시파일.
- 교안 실제 업로드는 후속 구현 대상으로 구분. 영상은 외부 URL, CSV/Preview는 현재 결과 파일 저장 불필요.
- 허용 확장자/MIME, 요청 전체 용량, 보관기간, 과제 삭제 후 복구 유예기간, 물리 삭제 재시도/고아 파일 청소 주기, 업로드 임시파일 만료/청소, 운영 MEDIA 접근 방식을 합의해야 한다.
- 공용 파일 ID와 업무 FK를 명시적으로 연결하는 방식이 필요하다. 현재 URL 기반 경로 복원은 공용 스토리지 전환 시 호환 검토가 필요하다.

위 항목은 현행 구현 확인과 미결정 사항 목록이며 새로운 정책을 임의로 확정한 것이 아니다.
