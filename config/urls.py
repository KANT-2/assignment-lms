"""
config/urls.py
공통 담당 전담 — 앱별 urls.py 를 include 만 한다 (여기서 직접 뷰 연결 금지).
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    # 인증 (Django 기본 뷰 사용). 로그인 템플릿은 registration/login.html 필요.
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),

    # 앱별 라우팅
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
