from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "공유 모델 (과제/제출/평가)"

    def ready(self):
        # Evaluation → Submission.final_score / is_locked 자동 동기화 (FR-013)
        from . import signals  # noqa: F401
