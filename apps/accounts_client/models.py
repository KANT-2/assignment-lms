"""
apps/accounts_client/models.py — 공통 담당 전담

외부 팀 구성 시스템(AX Evaluator)의 `accounts` DB 테이블을 읽기 전용으로 매핑한다.
- managed = False : 이 앱은 마이그레이션을 만들지 않는다.
- config.routers.AccountsRouter 가 이 모델들을 'accounts' DB 로 라우팅한다.
- 다른 앱은 이 모델을 직접 import 하지 말고 services.py 헬퍼로만 접근한다.
- 절대 write/save 하지 않는다.

⚠ 아래 필드 구성은 docs/assignment-lms-ERD.md §3.1 기준의 잠정안이다.
  AX Evaluator 실제 스키마가 확정되면 컬럼명·타입을 맞춰야 한다.
"""
from django.db import models


class AccountsUser(models.Model):
    email = models.EmailField()
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=20)  # "STUDENT" | "TUTOR"
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "accounts_user"

    def __str__(self):
        return f"{self.name} ({self.role})"


class TeamsTeam(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = "teams_team"

    def __str__(self):
        return self.name


class TeamsTeamMembership(models.Model):
    team_id = models.IntegerField()
    user_id = models.IntegerField()

    class Meta:
        managed = False
        db_table = "teams_team_membership"
