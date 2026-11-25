from django.contrib import admin

from audit_trail.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor_username",
        "category",
        "action",
        "outcome",
    )

    list_filter = (
        "category",
        "action",
        "outcome",
        "created_at",
    )

    search_fields = (
        "actor_username",
        "action",
        "description",
    )

    readonly_fields = (
        "actor",
        "actor_username",
        "category",
        "action",
        "outcome",
        "description",
        "details",
        "ip_address",
        "user_agent",
        "created_at",
    )

    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False