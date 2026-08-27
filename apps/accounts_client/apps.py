from django.apps import AppConfig


class AccountsClientConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts_client"
    label = "accounts_client"
    verbose_name = "외부 계정/팀 DB 참조"
