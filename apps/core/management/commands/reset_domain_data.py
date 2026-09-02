"""
로컬/스테이징 DB 의 도메인 데이터(과제 워크플로우 + 강의 콘텐츠 + 회차 점수)를
전부 삭제한다. 실운영 투입 전 테스트로 쌓인 가짜 데이터 정리용.

- default DB(assignment_lms) 만 건드린다. 외부 ax_evaluation 은 접근하지 않는다.
- 스키마/마이그레이션/media 디스크 파일/auth.User 는 건드리지 않는다 (DB 행만).
- GradingPolicy 는 싱글턴이라 지워도 get_solo() 가 기본값으로 다시 만든다.

    python manage.py reset_domain_data --yes
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import (
    AiEvaluation,
    Assignment,
    AssignmentFile,
    Evaluation,
    Lecture,
    Lesson,
    LessonMaterial,
    LessonVideo,
    Submission,
    SubmissionFile,
    Todo,
)
from apps.tutor.models import GradingPolicy, RoundScore

# 자식 → 부모 순. Assignment 는 소프트 삭제 모델이라 all_objects 매니저로 실삭제한다.
_TARGETS = [
    ("RoundScore", lambda: RoundScore.objects.all()),
    ("Evaluation", lambda: Evaluation.objects.all()),
    ("AiEvaluation", lambda: AiEvaluation.objects.all()),
    ("SubmissionFile", lambda: SubmissionFile.objects.all()),
    ("Submission", lambda: Submission.objects.all()),
    ("AssignmentFile", lambda: AssignmentFile.objects.all()),
    ("Assignment", lambda: Assignment.all_objects.all()),
    ("Todo", lambda: Todo.objects.all()),
    ("LessonMaterial", lambda: LessonMaterial.objects.all()),
    ("LessonVideo", lambda: LessonVideo.objects.all()),
    ("Lesson", lambda: Lesson.objects.all()),
    ("Lecture", lambda: Lecture.objects.all()),
    ("GradingPolicy", lambda: GradingPolicy.objects.all()),
]


class Command(BaseCommand):
    help = "도메인 데이터(과제·제출·평가·강의 콘텐츠·회차 점수)를 전부 삭제한다. DB 행만."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="확인 프롬프트 없이 즉시 삭제한다.",
        )

    def handle(self, *args, **options):
        counts = {name: qs().count() for name, qs in _TARGETS}
        total = sum(counts.values())

        self.stdout.write("삭제 대상 (default DB · assignment_lms):")
        for name, _ in _TARGETS:
            self.stdout.write(f"  {name:16} {counts[name]:>5}")
        self.stdout.write(f"  {'합계':16} {total:>5}")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("\n비울 데이터가 없습니다."))
            return

        if not options["yes"]:
            answer = input('\n정말 삭제합니다. "DELETE" 를 입력하세요: ')
            if answer.strip() != "DELETE":
                raise CommandError("취소했습니다.")

        with transaction.atomic():
            for name, qs in _TARGETS:
                deleted, _ = qs().delete()
                self.stdout.write(f"  삭제 {name:16} rows={deleted}")

        self.stdout.write(
            self.style.SUCCESS(
                "\n완료. GradingPolicy 는 다음 집계 시 기본값으로 재생성됩니다. "
                "media/ 디스크 파일은 그대로입니다."
            )
        )
