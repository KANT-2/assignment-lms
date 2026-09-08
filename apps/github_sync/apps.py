from django.apps import AppConfig


class GithubSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.github_sync"
    label = "github_sync"
    verbose_name = "GitHub 제출물 동기화"

    def ready(self):
        # SubmissionFile 생성 시 학생 GitHub 저장소로 push 큐잉/시도,
        # Evaluation 저장 시 학생 저장소에 튜터 피드백 이슈 생성/갱신
        from . import signals  # noqa: F401
