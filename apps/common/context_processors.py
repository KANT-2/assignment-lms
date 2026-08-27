"""
apps/common/context_processors.py — 공통 담당 전담

모든 템플릿에 현재 사용자 역할과 URL 네임스페이스를 넣어준다.
sidebar.html 등 공통 shell 이 role 로 메뉴를 분기하는 데 사용.
"""
from apps.accounts_client import services as accounts


def nav(request):
    role = None
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        if accounts.is_tutor(user.id):
            role = "TUTOR"
        elif accounts.is_student(user.id):
            role = "STUDENT"

    match = getattr(request, "resolver_match", None)
    return {
        "nav_role": role,
        "url_namespace": match.namespace if match else "",
        "url_name": match.url_name if match else "",
    }
