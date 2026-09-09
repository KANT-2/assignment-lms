from django.urls import path

from . import views

app_name = "github_sync"

urlpatterns = [
    path("connect/", views.connect, name="connect"),
    path("callback/", views.callback, name="callback"),
    path("disconnect/", views.disconnect, name="disconnect"),
    # 튜터도 위 callback/ 을 그대로 재사용한다 (세션 state 로 흐름 구분).
    # → OAuth App 에 콜백 URL 을 1개만 등록해도 됨.
    path("tutor/connect/", views.tutor_connect, name="tutor-connect"),
    path("tutor/disconnect/", views.tutor_disconnect, name="tutor-disconnect"),
]
