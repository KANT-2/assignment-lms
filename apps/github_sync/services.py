"""
apps/github_sync/services.py

제출물 → 학생 GitHub 저장소 push 오케스트레이션. 뷰 / 시그널 / 관리 커맨드가 공용으로 쓴다.

흐름:
    enqueue(submission)   제출·재제출 시 SubmissionPush 를 PENDING 으로 (개인 과제만)
    sync_one(push)        실제 커밋 1건 (repo 확보 → README + 파일 커밋)
    finalize_due(now)     마감 지난 제출물에 '최종 제출' 커밋 1회 더
    backfill_student(id)  학생이 뒤늦게 연결했을 때 기존 제출물 전부 enqueue

키(.env)가 없으면 enabled()=False → 시그널·UI 모두 no-op (LMS 기존 동작 불변).
"""
from __future__ import annotations

import hashlib
import logging
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts_client import services as accounts
from apps.common.preview import _storage_name
from apps.core.models import Submission

from . import github_api
from .github_api import GithubApiError
from .models import (
    FeedbackIssue,
    StudentGithubAccount,
    SubmissionPush,
    TutorGithubAccount,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
def enabled() -> bool:
    return bool(
        getattr(settings, "GITHUB_OAUTH_CLIENT_ID", None)
        and getattr(settings, "GITHUB_OAUTH_CLIENT_SECRET", None)
        and getattr(settings, "GITHUB_TOKEN_ENC_KEY", None)
    )


def _repo_name() -> str:
    return getattr(settings, "GITHUB_SUBMISSION_REPO_NAME", "lms-assignments")


# ─────────────────────────────────────────────────────────────
# 경로 / 메시지
# ─────────────────────────────────────────────────────────────
def _slug(text: str, fallback: str) -> str:
    return slugify(text or "", allow_unicode=True) or fallback


def _round_slug() -> str:
    try:
        rnd = accounts.get_current_round()
    except Exception:  # noqa: BLE001 — 라운드 조회 실패해도 push 는 진행
        rnd = None
    if rnd is None:
        return "round"
    return _slug(getattr(rnd, "title", ""), f"round-{getattr(rnd, 'id', 'x')}")


def _assignment_dir(assignment) -> str:
    return (
        f"{_round_slug()}/"
        f"{assignment.id:02d}-{_slug(assignment.title, 'assignment')}"
    )


def _commit_message(submission, *, final: bool) -> str:
    when = timezone.localtime(submission.submitted_at).strftime("%Y-%m-%d %H:%M")
    tail = "최종 제출" if final else "제출"
    return f"[{submission.assignment.title}] {tail} · {when}"


def _readme_body(submission) -> bytes:
    a = submission.assignment
    lines = [
        f"# {a.title}",
        "",
        f"- 마감: {timezone.localtime(a.due_at).strftime('%Y-%m-%d %H:%M')}",
        f"- 제출: {timezone.localtime(submission.submitted_at).strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 과제 설명",
        "",
        (a.description or "_(설명 없음)_"),
        "",
        "## 제출 설명",
        "",
        (submission.description or "_(없음)_"),
        "",
        "---",
        "_이 파일은 LMS 제출 시 자동 생성됩니다._",
    ]
    return ("\n".join(lines) + "\n").encode()


# ─────────────────────────────────────────────────────────────
# enqueue
# ─────────────────────────────────────────────────────────────
def enqueue(submission: Submission) -> SubmissionPush | None:
    """개인 제출물이면 PENDING 으로 (재)등록. 팀 제출물이면 무시하고 None."""
    if submission.student_id is None:  # 팀 과제 — 이번 범위 밖
        return None
    push, _created = SubmissionPush.objects.get_or_create(submission=submission)
    # 재제출이면 SYNCED/FAILED 였어도 다시 밀어 준다 (마감 최종본 플래그는 유지)
    push.state = SubmissionPush.State.PENDING
    push.error_message = ""
    push.save(update_fields=["state", "error_message", "updated_at"])
    return push


def backfill_student(student_id: int) -> int:
    """학생이 뒤늦게 GitHub 를 연결했을 때 — 기존 개인 제출물을 전부 큐에 넣는다."""
    count = 0
    for submission in Submission.objects.filter(
        student_id=student_id, assignment__is_team=False
    ):
        if enqueue(submission):
            count += 1
    return count


# ─────────────────────────────────────────────────────────────
# 실제 push
# ─────────────────────────────────────────────────────────────
def _read_file_bytes(submission_file) -> bytes:
    with default_storage.open(_storage_name(submission_file.file_url), "rb") as fh:
        return fh.read()


def _account_for(push: SubmissionPush) -> StudentGithubAccount | None:
    return StudentGithubAccount.objects.filter(
        student_id=push.submission.student_id
    ).first()


def _commit_author(account: StudentGithubAccount) -> tuple[str, str]:
    # 커밋은 학생 본인 이름으로. 이메일은 noreply (잔디 O, 개인 이메일 비노출).
    name = account.github_name or account.github_login
    email = f"{account.github_user_id}+{account.github_login}@users.noreply.github.com"
    return name, email


def sync_one(push: SubmissionPush) -> SubmissionPush:
    """제출물 1건을 학생 저장소에 커밋. 결과를 push 에 기록하고 저장한다."""
    submission = push.submission
    submission_file = submission.files.first()
    if submission_file is None:
        push.mark_attempt_failed("제출 파일이 없습니다.")
        push.save()
        return push

    account = _account_for(push)
    if account is None:
        push.state = SubmissionPush.State.NO_ACCOUNT
        push.last_attempt_at = timezone.now()
        push.save(update_fields=["state", "last_attempt_at", "updated_at"])
        return push

    try:
        content = _read_file_bytes(submission_file)
        token = account.token
        repo = account.repo_full_name or github_api.ensure_repo(
            token, account.github_login, _repo_name()
        )
        if repo != account.repo_full_name:
            account.repo_full_name = repo
            account.save(update_fields=["repo_full_name"])

        directory = _assignment_dir(submission.assignment)
        name, email = _commit_author(account)

        # README 먼저
        readme_path = f"{directory}/README.md"
        github_api.put_file(
            token, repo, readme_path, _readme_body(submission),
            _commit_message(submission, final=False) + " (README)",
            author_name=name, author_email=email,
            sha=github_api.get_file_sha(token, repo, readme_path),
        )

        # 제출 파일
        file_path = f"{directory}/{submission_file.file_name}"
        commit_sha = github_api.put_file(
            token, repo, file_path, content,
            _commit_message(submission, final=False),
            author_name=name, author_email=email,
            sha=github_api.get_file_sha(token, repo, file_path),
        )
    except (GithubApiError, OSError, ValueError) as exc:
        logger.warning("github sync 실패 (push#%s): %s", push.pk, exc)
        push.mark_attempt_failed(str(exc))
        push.save()
        account = _account_for(push)
        if account:
            account.last_error = str(exc)[:2000]
            account.save(update_fields=["last_error"])
        return push

    push.mark_synced(path=file_path, sha=commit_sha)
    push.attempts += 1
    push.save()
    account.last_synced_at = timezone.now()
    account.last_error = ""
    account.save(update_fields=["last_synced_at", "last_error"])
    return push


def finalize_due(now=None) -> int:
    """마감이 지난 SYNCED 제출물에 '최종 제출' 커밋을 1회 더 남긴다."""
    now = now or timezone.now()
    done = 0
    pushes = SubmissionPush.objects.filter(
        state=SubmissionPush.State.SYNCED,
        is_finalized=False,
        submission__assignment__due_at__lt=now,
    ).select_related("submission", "submission__assignment")
    for push in pushes:
        account = _account_for(push)
        submission_file = push.submission.files.first()
        if account is None or submission_file is None or not account.repo_full_name:
            continue
        try:
            token = account.token
            repo = account.repo_full_name
            directory = _assignment_dir(push.submission.assignment)
            file_path = f"{directory}/{submission_file.file_name}"
            name, email = _commit_author(account)
            sha = github_api.get_file_sha(token, repo, file_path)
            commit_sha = github_api.put_file(
                token, repo, file_path, _read_file_bytes(submission_file),
                _commit_message(push.submission, final=True),
                author_name=name, author_email=email, sha=sha,
            )
        except (GithubApiError, OSError, ValueError) as exc:
            logger.warning("github finalize 실패 (push#%s): %s", push.pk, exc)
            continue
        push.is_finalized = True
        push.finalized_commit_sha = commit_sha
        push.commit_sha = commit_sha
        push.save(update_fields=["is_finalized", "finalized_commit_sha", "commit_sha", "updated_at"])
        done += 1
    return done


def sync_pending(limit: int | None = None) -> dict:
    """PENDING / NO_ACCOUNT 상태 push 를 처리한다 (관리 커맨드용)."""
    qs = SubmissionPush.objects.filter(
        state__in=[SubmissionPush.State.PENDING, SubmissionPush.State.NO_ACCOUNT]
    ).select_related("submission", "submission__assignment").order_by("updated_at")
    if limit:
        qs = qs[:limit]
    result = {"synced": 0, "no_account": 0, "failed": 0}
    for push in qs:
        sync_one(push)
        if push.state == SubmissionPush.State.SYNCED:
            result["synced"] += 1
        elif push.state == SubmissionPush.State.NO_ACCOUNT:
            result["no_account"] += 1
        else:
            result["failed"] += 1
    return result


def try_sync_now(push: SubmissionPush) -> None:
    """제출 직후 즉시 시도 — 실패해도 조용히 넘어간다 (커맨드가 재시도)."""
    if not enabled():
        return
    try:
        sync_one(push)
    except Exception:  # noqa: BLE001 — 제출 흐름을 절대 막지 않는다
        logger.exception("github 즉시 동기화 중 예외 (push#%s)", push.pk)


# ─────────────────────────────────────────────────────────────
# 튜터 피드백 → 학생 저장소 이슈
# ─────────────────────────────────────────────────────────────
def tutor_account() -> TutorGithubAccount | None:
    """연결된 튜터 GitHub 계정 (운영상 1행). 미설정/미연결이면 None."""
    if not enabled():
        return None
    return TutorGithubAccount.objects.first()


def tutor_enabled() -> bool:
    return tutor_account() is not None


def _feedback_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()


def _submission_permalink(push: SubmissionPush, account: StudentGithubAccount) -> str:
    sha = push.finalized_commit_sha or push.commit_sha
    if not (account.repo_full_name and sha and push.committed_path):
        return account.repo_url
    return (
        f"https://github.com/{account.repo_full_name}/blob/{sha}/"
        + quote(push.committed_path)
    )


def _issue_title(submission, score: int) -> str:
    return f"[{submission.assignment.title}] 튜터 피드백 · {score}점"


def _issue_body(submission, evaluation, permalink: str, student_login: str) -> str:
    return "\n".join(
        [
            f"@{student_login} 님, 튜터 피드백이 등록되었습니다.",
            "",
            f"- **과제:** {submission.assignment.title}",
            f"- **점수:** {evaluation.score}점",
            f"- **제출 파일:** {permalink}",
            "",
            "---",
            "",
            (evaluation.feedback or "_(피드백 본문 없음)_"),
            "",
            "---",
            "_이 이슈는 LMS에서 튜터 평가 저장 시 자동으로 생성·갱신됩니다._",
        ]
    )


def _comment_body(evaluation) -> str:
    return "\n".join(
        [
            f"**피드백이 수정되었습니다.** (점수 {evaluation.score}점)",
            "",
            "---",
            "",
            (evaluation.feedback or "_(피드백 본문 없음)_"),
        ]
    )


def sync_feedback_issue(fi: FeedbackIssue) -> FeedbackIssue:
    """FeedbackIssue 1건 처리 — 이슈 생성 또는 코멘트 추가. 결과를 저장한다."""
    submission = fi.submission

    # 팀 과제는 학생 개인 저장소가 없어 대상 아님
    if submission.assignment.is_team or submission.student_id is None:
        fi.state = FeedbackIssue.State.SKIPPED
        fi.save(update_fields=["state", "updated_at"])
        return fi

    account = tutor_account()
    if account is None:
        fi.state = FeedbackIssue.State.PENDING
        fi.save(update_fields=["state", "updated_at"])
        return fi

    evaluation = getattr(submission, "evaluation", None)
    if evaluation is None:
        fi.state = FeedbackIssue.State.PENDING
        fi.save(update_fields=["state", "updated_at"])
        return fi

    student_account = StudentGithubAccount.objects.filter(
        student_id=submission.student_id
    ).first()
    push = SubmissionPush.objects.filter(submission=submission).first()
    if (
        student_account is None
        or push is None
        or push.state != SubmissionPush.State.SYNCED
    ):
        # 학생 저장소에 파일이 아직 올라가지 않음 — 나중에 커맨드가 재시도
        fi.state = FeedbackIssue.State.PENDING
        fi.save(update_fields=["state", "updated_at"])
        return fi

    new_hash = _feedback_hash(evaluation.feedback)
    if fi.issue_number and fi.feedback_hash == new_hash:
        return fi  # 이미 반영됨 — no-op

    token = account.token
    repo = student_account.repo_full_name
    permalink = _submission_permalink(push, student_account)

    try:
        if not fi.issue_number:
            issue = github_api.create_issue(
                token,
                repo,
                _issue_title(submission, evaluation.score),
                _issue_body(
                    submission, evaluation, permalink, student_account.github_login
                ),
            )
            fi.issue_number = issue["number"]
            fi.issue_url = issue["html_url"]
            fi.state = FeedbackIssue.State.CREATED
        else:
            github_api.add_issue_comment(
                token, repo, fi.issue_number, _comment_body(evaluation)
            )
            fi.state = FeedbackIssue.State.COMMENTED
    except (GithubApiError, OSError, ValueError) as exc:
        logger.warning("피드백 이슈 동기화 실패 (submission#%s): %s", submission.pk, exc)
        fi.mark_attempt_failed(str(exc))
        fi.save()
        account.last_error = str(exc)[:2000]
        account.save(update_fields=["last_error"])
        return fi

    fi.feedback_hash = new_hash
    fi.attempts += 1
    fi.error_message = ""
    fi.last_attempt_at = timezone.now()
    fi.save()
    account.last_used_at = timezone.now()
    account.last_error = ""
    account.save(update_fields=["last_used_at", "last_error"])
    return fi


def enqueue_feedback_issue(submission: Submission) -> FeedbackIssue | None:
    """제출물의 튜터 피드백을 이슈로 (재)동기화한다. 팀 과제면 None."""
    if submission.student_id is None:
        return None
    fi, _created = FeedbackIssue.objects.get_or_create(submission=submission)
    # 재평가면 SKIPPED/FAILED 였어도 다시 시도할 수 있게 되돌린다 (개인 과제 한정).
    if not submission.assignment.is_team and fi.state in (
        FeedbackIssue.State.SKIPPED,
        FeedbackIssue.State.FAILED,
    ):
        fi.state = FeedbackIssue.State.PENDING
        fi.attempts = 0
        fi.save(update_fields=["state", "attempts", "updated_at"])
    return sync_feedback_issue(fi)


def sync_pending_feedback_issues(limit: int | None = None) -> dict:
    """PENDING 상태 FeedbackIssue 를 처리한다 (관리 커맨드용)."""
    qs = (
        FeedbackIssue.objects.filter(state=FeedbackIssue.State.PENDING)
        .select_related("submission", "submission__assignment")
        .order_by("updated_at")
    )
    if limit:
        qs = qs[:limit]
    result = {"created": 0, "commented": 0, "pending": 0, "failed": 0}
    for fi in qs:
        sync_feedback_issue(fi)
        if fi.state == FeedbackIssue.State.CREATED:
            result["created"] += 1
        elif fi.state == FeedbackIssue.State.COMMENTED:
            result["commented"] += 1
        elif fi.state == FeedbackIssue.State.FAILED:
            result["failed"] += 1
        else:
            result["pending"] += 1
    return result


def try_feedback_issue_now(submission: Submission) -> None:
    """평가 저장 직후 즉시 시도 — 실패해도 조용히 넘어간다 (커맨드가 재시도)."""
    if not tutor_enabled():
        return
    try:
        enqueue_feedback_issue(submission)
    except Exception:  # noqa: BLE001 — 평가 저장 흐름을 절대 막지 않는다
        logger.exception("피드백 이슈 즉시 동기화 중 예외 (submission#%s)", submission.pk)
