"""
apps/common/middleware.py — 공통 담당 전담

DevAutoLoginMiddleware
    settings.DEV_SKIP_AUTH=True 일 때, 인증되지 않은 요청을 고정 dev 유저로
    로그인 처리한다. 네트워크/AX DB 없이 화면·테스트를 돌리기 위한 **개발 전용** 폴백
    (평소엔 실제 로그인 — apps.accounts_client.backends.AxPasswordBackend).

    - 뷰의 @login_required / request.user.id 가 그대로 동작한다.
    - 역할(튜터/학생)은 settings.DEV_ROLE 로 정하며, accounts_client.services 가
      같은 값을 보고 is_tutor / is_student 를 판단한다.
    - config.settings.dev 에서만 MIDDLEWARE 에 추가한다. prod 에서는 절대 금지.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import MiddlewareNotUsed


class DevAutoLoginMiddleware:
    def __init__(self, get_response):
        if not getattr(settings, "DEV_SKIP_AUTH", False):
            raise MiddlewareNotUsed  # 플래그 꺼져 있으면 미들웨어 자체를 비활성화
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            request.user = self._dev_user()
        return self.get_response(request)

    @staticmethod
    def _dev_user():
        User = get_user_model()
        dev_id = getattr(settings, "DEV_USER_ID", 999999)
        # 고정 id — 실제 accounts_user id 와 겹치지 않게. 예전 dev 유저(다른 id)가 남아
        # 있으면 username 충돌하므로 정리한다.
        User.objects.filter(username="dev").exclude(pk=dev_id).delete()
        user, _ = User.objects.get_or_create(
            pk=dev_id,
            defaults={
                "username": "dev",
                "email": "dev@local",
                "is_staff": True,      # /admin/ 도 함께 열람 가능하게
                "is_superuser": True,
            },
        )
        # login() 없이 request 에만 붙이므로 backend 지정이 필요 없다.
        return user
