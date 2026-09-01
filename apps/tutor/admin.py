from django.contrib import admin

from .models import GradingPolicy, RoundScore


@admin.register(GradingPolicy)
class GradingPolicyAdmin(admin.ModelAdmin):
    """싱글턴 — 항상 1행만 편집. 추가/삭제는 막는다."""

    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not GradingPolicy.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RoundScore)
class RoundScoreAdmin(admin.ModelAdmin):
    """회차 마감 스냅샷 — 조회 전용. 수정은 화면에서 재마감으로만."""

    list_display = ("round_id", "round_title", "student_name", "total", "team_included", "closed_at")
    list_filter = ("round_id", "team_included")
    search_fields = ("student_name", "student_id")
    ordering = ("-closed_at", "student_name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
