from django.urls import path

from . import views

app_name = "github_sync"

urlpatterns = [
    path("connect/", views.connect, name="connect"),
    path("callback/", views.callback, name="callback"),
    path("disconnect/", views.disconnect, name="disconnect"),
    path("tutor/connect/", views.tutor_connect, name="tutor-connect"),
    path("tutor/callback/", views.tutor_callback, name="tutor-callback"),
    path("tutor/disconnect/", views.tutor_disconnect, name="tutor-disconnect"),
]
