"""
config/urls.py
공통 담당 전담 — 앱별 urls.py 를 include 만 한다 (여기서 직접 뷰 연결 금지).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts_client import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # 인증 — ax_evaluation.accounts_user 자격증명으로 로그인 (apps.accounts_client.backends)
    path("accounts/login/", auth_views.login_view, name="login"),
    path("accounts/logout/", auth_views.logout_view, name="logout"),

    # 앱별 라우팅
    path("github/", include("apps.github_sync.urls")),
    path("", include("apps.student.urls")),
    path("tutor/", include("apps.tutor.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    try:
        import debug_toolbar  # noqa: F401

        urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
    except ImportError:
        pass
