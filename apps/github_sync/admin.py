from django.contrib import admin

from .models import StudentGithubAccount, SubmissionPush


@admin.register(StudentGithubAccount)
class StudentGithubAccountAdmin(admin.ModelAdmin):
    list_display = ("student_id", "github_login", "repo_full_name", "last_synced_at")
    search_fields = ("student_id", "github_login")
    # 토큰은 노출하지 않는다
    exclude = ("access_token_encrypted",)
    readonly_fields = ("connected_at", "last_synced_at", "last_error")


@admin.register(SubmissionPush)
class SubmissionPushAdmin(admin.ModelAdmin):
    list_display = ("submission_id", "state", "attempts", "is_finalized", "synced_at")
    list_filter = ("state", "is_finalized")
    readonly_fields = tuple(f.name for f in SubmissionPush._meta.fields)
