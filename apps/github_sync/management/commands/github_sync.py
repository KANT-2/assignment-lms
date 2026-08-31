"""
학생 제출물 → GitHub 동기화 배치.

cron / systemd timer 로 5분 간격 실행 권장:
    */5 * * * * cd /app && python manage.py github_sync

동작:
    - PENDING / NO_ACCOUNT 상태 제출물 push 재시도
    - 마감이 지난 제출물에 '최종 제출' 커밋 1회
    - --backfill <student_id> 로 특정 학생 기존 제출물 재큐잉 (없으면 전체)
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.github_sync import services
from apps.github_sync.models import StudentGithubAccount


class Command(BaseCommand):
    help = "학생 제출물을 학생 GitHub 저장소로 동기화한다."

    def add_arguments(self, parser):
        parser.add_argument("--backfill", type=int, nargs="?", const=-1, default=None,
                            help="학생 id (생략 시 연결된 학생 전체) 의 기존 제출물을 재큐잉")
        parser.add_argument("--limit", type=int, default=None,
                            help="이번 실행에서 처리할 최대 건수")

    def handle(self, *args, **options):
        if not services.enabled():
            self.stderr.write("GitHub 연동이 설정되지 않았습니다 (.env 확인). 종료.")
            return

        backfill = options["backfill"]
        if backfill is not None:
            if backfill == -1:
                ids = StudentGithubAccount.objects.values_list("student_id", flat=True)
            else:
                ids = [backfill]
            total = sum(services.backfill_student(sid) for sid in ids)
            self.stdout.write(f"backfill: {total}건 재큐잉")

        result = services.sync_pending(limit=options["limit"])
        self.stdout.write(
            f"sync_pending: 동기화 {result['synced']} · 미연결 {result['no_account']} · 실패 {result['failed']}"
        )

        finalized = services.finalize_due(timezone.now())
        self.stdout.write(f"finalize_due: 최종본 커밋 {finalized}건")
