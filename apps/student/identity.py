"""학생 화면에서 외부 계정/팀 조회에 사용할 사용자 ID."""

from django.conf import settings


DEV_STUDENT_ID = 11  # accounts_client.services 가 제공하는 가상 김학생


def external_student_id(request) -> int:
    """개발 로그인 우회 중에는 김학생, 실제 로그인에서는 로그인 사용자 ID."""
    if getattr(settings, "DEV_SKIP_AUTH", False):
        return DEV_STUDENT_ID
    return request.user.id
