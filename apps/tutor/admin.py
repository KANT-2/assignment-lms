from django.contrib import admin

from .models import GradingPolicy


@admin.register(GradingPolicy)
class GradingPolicyAdmin(admin.ModelAdmin):
    """싱글턴 — 항상 1행만 편집. 추가/삭제는 막는다."""

    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not GradingPolicy.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
