from django.urls import path

from . import views

app_name = "github_sync"

urlpatterns = [
    path("connect/", views.connect, name="connect"),
    path("callback/", views.callback, name="callback"),
    path("disconnect/", views.disconnect, name="disconnect"),
    path("tutor/connect/", views.tutor_connect, name="tutor-connect"),
    # GitHub OAuth App 에 등록된 콜백 URL(/github/callback/)의 하위 경로여야
    # redirect_uri 가 승인된다 → 학생 콜백과 같은 prefix 아래 둔다.
    path("callback/tutor/", views.tutor_callback, name="tutor-callback"),
    path("tutor/disconnect/", views.tutor_disconnect, name="tutor-disconnect"),
]
