"""
config/routers.py
공통 담당 전담 — DB 라우터.

apps.accounts_client 앱의 모델(외부 계정/팀 DB, managed=False)은
'accounts' DB 로 읽기만 하고, 그 외 모든 모델은 'default' DB(이 프로젝트 전용)를 쓴다.
"""

ACCOUNTS_APP = "accounts_client"
ACCOUNTS_DB = "accounts"


class AccountsRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label == ACCOUNTS_APP:
            return ACCOUNTS_DB
        return None

    def db_for_write(self, model, **hints):
        # 외부 DB 는 읽기 전용 — 쓰기 라우팅 안 함
        if model._meta.app_label == ACCOUNTS_APP:
            return ACCOUNTS_DB
        return None

    def allow_relation(self, obj1, obj2, **hints):
        labels = {obj1._meta.app_label, obj2._meta.app_label}
        if labels <= {ACCOUNTS_APP}:
            return True
        if ACCOUNTS_APP in labels:
            # 서로 다른 DB 간 FK 관계는 허용하지 않음 (id 값만 저장해서 참조)
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == ACCOUNTS_APP:
            # accounts_client 모델은 어느 DB 에도 마이그레이션하지 않음
            return False
        if db == ACCOUNTS_DB:
            # accounts DB 에는 이 프로젝트의 어떤 마이그레이션도 적용하지 않음
            return False
        return True
