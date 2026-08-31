"""
apps/github_sync/models.py

학생 제출물을 학생 본인 GitHub 저장소로 자동 push 하기 위한 상태 저장소.

- apps/core/models.py (공통 담당 전담) 는 건드리지 않는다.
  Submission 과는 OneToOne FK 로만 연결한다.
- student_id 는 core.Submission.student_id 와 같은 체계 (accounts_user.id, FK 아님).
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.models import Submission

from . import crypto

MAX_ATTEMPTS = 5


class StudentGithubAccount(models.Model):
    """학생 1명당 1행 — GitHub OAuth 연결 정보 + 대상 저장소."""

    student_id = models.IntegerField(unique=True, help_text="accounts_user.id (FK 아님)")

    github_user_id = models.BigIntegerField()
    github_login = models.CharField(max_length=100)
    github_name = models.CharField(max_length=200, blank=True)

    # Fernet 로 암호화된 액세스 토큰 (평문 저장 금지). 접근은 token / set_token 으로만.
    access_token_encrypted = models.TextField()
    token_scope = models.CharField(max_length=200, blank=True)

    repo_full_name = models.CharField(
        max_length=200, blank=True, help_text="최초 저장소 확보 후 캐시 (예: nelson/lms-assignments)"
    )

    connected_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = "github_student_account"

    def __str__(self):
        return f"{self.student_id} → @{self.github_login}"

    # --- 토큰 접근 ---
    @property
    def token(self) -> str:
        return crypto.decrypt(self.access_token_encrypted)

    def set_token(self, raw: str) -> None:
        self.access_token_encrypted = crypto.encrypt(raw)

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.repo_full_name}" if self.repo_full_name else ""


class SubmissionPush(models.Model):
    """제출물 1건의 GitHub 동기화 상태."""

    class State(models.TextChoices):
        PENDING = "PENDING", "대기"
        SYNCED = "SYNCED", "동기화됨"
        FAILED = "FAILED", "실패"
        NO_ACCOUNT = "NO_ACCOUNT", "GitHub 미연결"

    submission = models.OneToOneField(
        Submission, on_delete=models.CASCADE, related_name="github_push"
    )

    state = models.CharField(
        max_length=12, choices=State.choices, default=State.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    committed_path = models.CharField(max_length=500, blank=True)
    commit_sha = models.CharField(max_length=64, blank=True)

    is_finalized = models.BooleanField(
        default=False, help_text="마감 후 '최종 제출' 커밋까지 완료"
    )
    finalized_commit_sha = models.CharField(max_length=64, blank=True)

    error_message = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "github_submission_push"
        indexes = [models.Index(fields=["state"])]

    def __str__(self):
        return f"push#{self.pk} submission#{self.submission_id} {self.state}"

    @property
    def commit_url(self) -> str:
        account = StudentGithubAccount.objects.filter(
            student_id=self.submission.student_id
        ).first()
        if account and account.repo_full_name and self.commit_sha:
            return f"https://github.com/{account.repo_full_name}/commit/{self.commit_sha}"
        return ""

    def mark_synced(self, *, path: str, sha: str) -> None:
        self.state = self.State.SYNCED
        self.committed_path = path
        self.commit_sha = sha
        self.synced_at = timezone.now()
        self.last_attempt_at = timezone.now()
        self.error_message = ""

    def mark_attempt_failed(self, message: str) -> None:
        self.attempts += 1
        self.last_attempt_at = timezone.now()
        self.error_message = message[:2000]
        self.state = (
            self.State.FAILED if self.attempts >= MAX_ATTEMPTS else self.State.PENDING
        )
