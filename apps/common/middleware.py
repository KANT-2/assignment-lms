"""
apps/common/middleware.py — 공통 담당 전담

DevAutoLoginMiddleware
    settings.DEV_SKIP_AUTH=True 일 때, 인증되지 않은 요청을 고정 dev 유저로
    로그인 처리한다. 인증 방식(PRD 9장)이 확정되기 전까지 로그인 화면 없이
    학생/튜터 화면을 보기 위한 **개발 전용** 장치.

    - 뷰의 @login_required / request.user.id 가 그대로 동작한다.
    - 역할(튜터/학생)은 settings.DEV_ROLE 로 정하며, accounts_client.services 가
      같은 값을 보고 is_tutor / is_student 를 판단한다.
    - config.settings.dev 에서만 MIDDLEWARE 에 추가한다. prod 에서는 절대 금지.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import MiddlewareNotUsed

DEV_USERNAME = "dev"


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
        user, _ = User.objects.get_or_create(
            username=DEV_USERNAME,
            defaults={
                "email": "dev@local",
                "is_staff": True,      # /admin/ 도 함께 열람 가능하게
                "is_superuser": True,
            },
        )
        # login() 없이 request 에만 붙이므로 backend 지정이 필요 없다.
        return user
