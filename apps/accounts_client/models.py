"""
apps/accounts_client/models.py — 공통 담당 전담

AX2 통합 플랫폼(`ax_evaluation` DB)이 제공하는 **VIEW 2개 + 회차 테이블 1개**를 읽기 전용으로 매핑한다.

- managed = False : 이 앱은 마이그레이션을 만들지 않는다. `migrate` 도 이 DB 를 건드리지 않음
  (config.routers.AccountsRouter.allow_migrate → False).
- config.routers.AccountsRouter 가 이 모델들을 'accounts' DB(=ax_evaluation)로 라우팅.
- 다른 앱은 이 모델을 직접 import 하지 말고 services.py 헬퍼로만 접근. 절대 write 금지.

VIEW 정의는 AX2 팀 소유 (문서: "AX2 통합 플랫폼 DB VIEW 제공 안내").
로그인 인증은 `accounts_user` 테이블(VIEW 아님)의 password/승인상태를 읽어서 처리한다
(backends.AxPasswordBackend). 역시 읽기 전용 — 절대 write 하지 않는다.
"""
from django.db import models


class AxUserLogin(models.Model):
    """
    ax_user_team_login_view — 사용자별 1행 (해당 유저의 **가장 최근 라운드** 팀 기준).
    role / 이메일 / 승인상태는 여기에만 있다. 튜터·admin 은 팀/라운드가 NULL (라운드 미참가).
    """

    user_id = models.BigIntegerField(primary_key=True)
    user_email = models.CharField(max_length=254)
    primary_email = models.CharField(max_length=254, null=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    display_name_snapshot = models.CharField(max_length=150, null=True)
    role = models.CharField(max_length=20)  # "student" | "tutor" | "admin"
    approval_status = models.CharField(max_length=20, null=True)  # "approved" | "pending"
    is_active = models.BooleanField()
    round_id = models.BigIntegerField(null=True)
    team_id = models.BigIntegerField(null=True)
    team_name = models.CharField(max_length=100, null=True)

    class Meta:
        managed = False
        db_table = "ax_user_team_login_view"

    def __str__(self):
        return f"{self.name} ({self.role})"

    @property
    def name(self):
        return self.display_name_snapshot or self.first_name or self.user_email

    @property
    def email(self):
        return self.primary_email or self.user_email


class AccountsUser(models.Model):
    """
    accounts_user 테이블 (VIEW 아님) — 로그인 인증 전용 읽기 매핑.
    password 는 Django 표준 해시(pbkdf2_sha256$...)라 check_password 로 그대로 검증된다.
    승인 규칙: is_active=True AND approval_status='approved' 여야 로그인 허용.
    """

    id = models.BigIntegerField(primary_key=True)
    email = models.EmailField()
    password = models.CharField(max_length=128)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20)
    approval_status = models.CharField(max_length=20)
    is_active = models.BooleanField()
    is_staff = models.BooleanField()
    is_superuser = models.BooleanField()

    class Meta:
        managed = False
        db_table = "accounts_user"

    def __str__(self):
        return f"{self.first_name or self.email} ({self.role})"

    @property
    def is_login_allowed(self):
        return self.is_active and self.approval_status == "approved"


class EvaluationRound(models.Model):
    """
    rounds_evaluationround 테이블 — 평가 회차(라운드) 자체. AX2 가 직접 읽기 승인.
    회차 점수 마감(docs/assignment-lms-round-close.md)에서 회차 기간을 얻는 데만 쓴다.
    필요한 컬럼만 매핑 (원본은 19컬럼). 절대 write 금지.
    """

    id = models.BigIntegerField(primary_key=True)
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20)  # "IN_PROGRESS" | "COMPLETED" 등
    evaluation_start_at = models.DateTimeField(null=True)
    evaluation_end_at = models.DateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "rounds_evaluationround"

    def __str__(self):
        return f"{self.title} (round {self.id})"


class RoundTeamMember(models.Model):
    """
    user_round_team_view — (참가자 × 라운드) 팀 소속. participant 당 1행.
    라운드마다 팀이 재편성되므로 team 조회는 **반드시 round_id 로 스코프**한다.
    INNER JOIN 이라 라운드 참가자(=학생)만 나온다.
    """

    participant_id = models.BigIntegerField(primary_key=True)
    user_id = models.BigIntegerField()
    email = models.CharField(max_length=254)
    round_id = models.BigIntegerField()
    round_title = models.CharField(max_length=200)
    round_status = models.CharField(max_length=20)  # "IN_PROGRESS" | "COMPLETED"
    student_number_snapshot = models.CharField(max_length=50, null=True)
    display_name_snapshot = models.CharField(max_length=150, null=True)
    team_id = models.BigIntegerField()
    team_number = models.SmallIntegerField(null=True)
    team_name = models.CharField(max_length=100)
    # 프로젝트(팀 활동) 회차 식별자 + 기간. 라운드별로 동일 (팀 무관).
    project_info_id = models.BigIntegerField(null=True)
    team_start = models.DateField(null=True)
    team_end = models.DateField(null=True)

    class Meta:
        managed = False
        db_table = "user_round_team_view"

    def __str__(self):
        return f"{self.name} · {self.team_name} (round {self.round_id})"

    @property
    def name(self):
        return self.display_name_snapshot or self.email
