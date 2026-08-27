"""
apps/core/signals.py

Evaluation(튜터 공식 평가) 저장/수정 시 Submission.final_score를 자동으로 동기화하고,
동시에 Submission.is_locked를 true로 바꿔 재제출을 차단한다 (FR-013).

apps.py의 AppConfig.ready()에서 반드시 import 해줘야 실제로 동작함:

    # apps/core/apps.py
    class CoreConfig(AppConfig):
        default_auto_field = "django.db.models.BigAutoField"
        name = "apps.core"

        def ready(self):
            import apps.core.signals  # noqa
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Evaluation


@receiver(post_save, sender=Evaluation)
def sync_final_score(sender, instance: Evaluation, **kwargs):
    submission = instance.submission
    submission.final_score = instance.score
    submission.is_locked = True
    submission.save(update_fields=["final_score", "is_locked"])