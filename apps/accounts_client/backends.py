"""
apps/accounts_client/backends.py — 공통 담당 전담

AxPasswordBackend
    ax_evaluation.accounts_user 의 이메일 + 비밀번호로 인증한다.
    - accounts_user 는 읽기만 한다 (password/승인상태 SELECT). AX DB 에 write 없음.
    - 인증 성공 시 우리 DB(default)에 로컬 auth.User 를 미러한다:
        · id = accounts_user.id  (→ request.user.id == accounts_user.id 유지)
        · email/이름/is_staff/is_superuser 를 로그인마다 AX 값으로 갱신 (로컬 캐시)
        · 비밀번호는 미러에 저장 안 함 (set_unusable_password) — 로그인은 이 백엔드로만
    - 세션·last_login 은 로컬 auth.User 기준이라 전부 default DB 에 저장된다.

승인 규칙(AX 원본과 동일): is_active AND approval_status='approved'.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password


def _lookup_account(email):
    from .models import AccountsUser

    if not email:
        return None
    return AccountsUser.objects.filter(email__iexact=email.strip()).first()


class AxPasswordBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        email = email or username
        account = _lookup_account(email)
        if account is None or not password:
            return None
        if not check_password(password, account.password):
            return None
        if not account.is_login_allowed:
            # 비번은 맞지만 미승인/비활성 — 뷰에서 별도 안내 (여기선 인증 실패로 처리)
            return None
        return self._mirror(account)

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    @staticmethod
    def _mirror(account):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            id=account.id, defaults={"username": f"ax_{account.id}"}
        )
        user.email = account.email
        user.first_name = account.first_name or ""
        user.last_name = account.last_name or ""
        user.is_staff = account.is_staff
        user.is_superuser = account.is_superuser
        user.is_active = True
        user.set_unusable_password()
        user.save()
        return user


def account_login_status(email):
    """뷰에서 실패 사유 안내용: 계정이 있으나 미승인이면 True 반환."""
    account = _lookup_account(email)
    return bool(account and not account.is_login_allowed)
