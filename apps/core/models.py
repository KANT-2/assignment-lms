"""
apps/core/models.py — 공통 담당 전담 · 이 프로젝트의 공유 모델

ERD v6 기준. 이 프로젝트 전용 PostgreSQL('default' DB)에 실제로 생성되는 테이블.

⚠ 외부 참조 방식: 방법 B 채택
    accounts_user, teams_team, teams_team_membership 등 AX Evaluator DB의 테이블은
    FK로 걸지 않고 IntegerField로 ID만 저장한다 (on_delete/related_name 옵션 없음).
    예: student_id = models.IntegerField()  # accounts_user.id 값, FK 아님

⚠ 이 파일은 공통 담당자 전담 영역입니다. 필드 변경/추가 시 팀 공유 후 진행해주세요.
"""

from django.db import models
from django.utils import timezone


# =========================================================
# 강의 / 교안  (FR-015, FR-016, BR-001)
# =========================================================

class Lecture(models.Model):
    """
    강의(과목) 자체. BR-001: 단일 강의 운영 → 시스템 내 항상 1행만 존재.
    """
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lecture"

    def __str__(self):
        return self.title

    DEFAULT_TITLE = "AX 실무 프로젝트 집중 과정"

    @classmethod
    def get_singleton(cls):
        """BR-001 단일 강의. 읽기·쓰기가 항상 같은 행을 가리키도록 이 헬퍼만 사용한다.
        (제목으로 조회하면 제목이 바뀔 때 유령 행이 생긴다 — id 순 최솟값 고정.)"""
        lecture = cls.objects.order_by("id").first()
        if lecture is None:
            lecture = cls.objects.create(title=cls.DEFAULT_TITLE)
        return lecture


class Lesson(models.Model):
    """
    강의 1회차(수업). 튜터가 제목·날짜·블로그링크·교안을 올리고,
    수업 종료 후 유튜브 링크(video_url)를 추가.
    """
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    lesson_date = models.DateField()
    blog_link = models.URLField(blank=True, null=True)
    video_url = models.URLField(blank=True, null=True, help_text="수업 종료 후 튜터가 추가, nullable")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lesson"
        ordering = ["lesson_date"]

    def __str__(self):
        return self.title


class LessonMaterial(models.Model):
    """
    회차별 교안 (복수). 업로드 파일(kind=FILE) 또는 외부 링크(kind=LINK).
    """
    class Kind(models.TextChoices):
        FILE = "FILE", "파일"
        LINK = "LINK", "링크"

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="materials")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=200)
    file_url = models.URLField(blank=True, null=True, help_text="kind=FILE인 경우")
    link_url = models.URLField(blank=True, null=True, help_text="kind=LINK인 경우")

    class Meta:
        db_table = "lesson_material"


# =========================================================
# 과제 / 제출 / 평가  (FR-001~014, BR-004~009)
# =========================================================

class AssignmentQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)


class AssignmentManager(models.Manager):
    """기본 매니저 — 소프트 삭제된 과제(deleted_at IS NOT NULL)는 제외 (FR-002)."""

    def get_queryset(self):
        return AssignmentQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


class Assignment(models.Model):
    """
    과제. 마감일·필수/선택·지각허용·개인/팀 속성 보유.
    삭제는 deleted_at 소프트 삭제로 undo 지원 (FR-002).
    """

    class WeightTier(models.TextChoices):
        HIGH = "HIGH", "상"
        MID = "MID", "중"
        LOW = "LOW", "하"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_at = models.DateTimeField()
    is_required = models.BooleanField(default=True)
    allow_late = models.BooleanField(default=True)
    is_team = models.BooleanField(default=False, help_text="true=팀 과제, false=개인 과제")

    # 성적 집계용 가중치 등급. 실제 가중치 숫자·감점/가산점 정책은
    # 추후 GRADING_POLICY 테이블에서 별도 관리 예정 (팀 논의 대기 중).
    weight_tier = models.CharField(
        max_length=10, choices=WeightTier.choices, default=WeightTier.MID
    )

    created_by = models.IntegerField(help_text="accounts_user.id 참조, FK 아님 (튜터)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(
        null=True, blank=True, help_text="소프트 삭제. null=활성 상태, undo는 이 값 복구로 처리"
    )

    objects = AssignmentManager()                     # 기본: 활성 과제만
    all_objects = AssignmentQuerySet.as_manager()     # 삭제 포함 전체 (관리자·복구용)

    class Meta:
        db_table = "assignment"
        # 관계 역참조(submission.assignment 등)는 소프트 삭제된 과제도 볼 수 있어야 하므로
        # base manager 는 전체를 반환하는 매니저로 지정한다.
        base_manager_name = "all_objects"

    def __str__(self):
        return self.title

    def delete(self, using=None, keep_parents=False):
        """소프트 삭제 — 실제 row 를 지우지 않고 deleted_at 타임스탬프만 채운다 (FR-002)."""
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=["deleted_at", "updated_at"])

    def restore(self):
        """소프트 삭제 취소 (undo) — deleted_at 을 다시 null 로 되돌린다."""
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        """실제 row 삭제 (정리 작업 전용)."""
        return super().delete(using=using, keep_parents=keep_parents)


class Submission(models.Model):
    """
    제출물. (assignment, 제출단위) 당 1행 — 재제출은 덮어쓰기이고 이력을 남기지 않음.
    개인 과제는 student_id만, 팀 과제는 team_id만 채워져야 함 (배타 규칙, FR-009/BR-005).
    """

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")

    student_id = models.IntegerField(
        null=True, blank=True, help_text="accounts_user.id 참조, 개인 과제인 경우"
    )
    team_id = models.IntegerField(
        null=True, blank=True, help_text="teams_team.id 참조, 팀 과제인 경우 (팀장만 제출)"
    )

    description = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    last_editor_id = models.IntegerField(
        null=True, blank=True,
        help_text="accounts_user.id — 최초 제출/마지막 재제출을 수행한 사용자 (팀 과제 책임소재)",
    )
    is_locked = models.BooleanField(
        default=False, help_text="EVALUATION 최초 저장 시 true, 재제출 차단"
    )

    # EVALUATION.score 저장/수정 시 시그널로 자동 동기화되는 캐시값.
    # null이면 "피드백 대기", 값이 있으면 "피드백 완료" (목업 화면 상태와 대응).
    final_score = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "submission"
        constraints = [
            # student_id / team_id 중 정확히 하나만 non-null (DB 레벨 방어선).
            # "is_team 값과의 일치"는 다른 테이블(assignment) 참조라 DB CHECK 로는 불가 →
            # 그 부분은 clean() 에서만 검증한다.
            models.CheckConstraint(
                condition=(
                    models.Q(student_id__isnull=False, team_id__isnull=True)
                    | models.Q(student_id__isnull=True, team_id__isnull=False)
                ),
                name="submission_student_id_xor_team_id",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        # 배타 규칙 검증 (백엔드 validation — DB CHECK 제약은 별도 마이그레이션에서 추가 예정)
        if self.assignment.is_team:
            if not self.team_id or self.student_id:
                raise ValidationError("팀 과제는 team_id만 채워져야 합니다.")
        else:
            if not self.student_id or self.team_id:
                raise ValidationError("개인 과제는 student_id만 채워져야 합니다.")

    def __str__(self):
        return f"Submission#{self.pk} for Assignment#{self.assignment_id}"


class SubmissionFile(models.Model):
    """
    제출 첨부파일 (복수 가능). kind로 미리보기 방식 결정.
    """

    class Kind(models.TextChoices):
        PY = "PY", ".py"
        IPYNB = "IPYNB", ".ipynb"
        OTHER = "OTHER", "그 외"

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="files")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    file_url = models.URLField()
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField(help_text="바이트 단위")

    class Meta:
        db_table = "submission_file"


class AiEvaluation(models.Model):
    """
    AI 1차 평가 (점수+코멘트). 제출물당 1행, 재생성 시 갱신.
    현재는 시뮬레이션이며, 이전 결과는 이력 없이 덮어씀.
    """

    submission = models.OneToOneField(
        Submission, on_delete=models.CASCADE, related_name="ai_evaluation"
    )
    score = models.IntegerField(help_text="0 to 100")
    comment = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_evaluation"


class Evaluation(models.Model):
    """
    튜터의 공식 평가 (점수+피드백). 최초 저장 시 제출물 잠금, 이후 수정 가능.
    저장/수정 시 Submission.final_score에 자동 동기화됨 (signals.py 참고).
    """

    submission = models.OneToOneField(
        Submission, on_delete=models.CASCADE, related_name="evaluation"
    )
    score = models.IntegerField(help_text="0 to 100")
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "evaluation"


# =========================================================
# 학생 개인 TODO
# =========================================================

class Todo(models.Model):
    student_id = models.IntegerField(help_text="accounts_user.id 참조, FK 아님")
    content = models.CharField(max_length=500)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "todo"