
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Personal Information",
            {"fields": ("first_name", "last_name", "email")},
        ),
        (
            "Organization",
            {"fields": ("role", "department", "employee_id", "phone")},
        ),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser")},
        ),
        (
            "Important Dates",
            {"fields": ("last_login", "date_joined")},
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Organization",
            {"fields": ("role", "department", "employee_id", "phone")},
        ),
    )

    list_display = (
        "username",
        "email",
        "role",
        "department",
        "is_active",
        "is_staff",
    )

    list_filter = (
        "role",
        "department",
        "is_active",
        "is_staff",
    )

    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "employee_id",
    )

    autocomplete_fields = ("department",)
    list_select_related = ("department",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        if not request.user.is_superuser:
            queryset = queryset.filter(is_superuser=False)

        return queryset

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)

        restricted_fields = set()

        if not request.user.is_superuser:
            restricted_fields.update({"is_staff", "is_superuser"})

        if obj and obj.pk == request.user.pk:
            restricted_fields.update({"role", "is_active"})

        updated_fieldsets = []

        for name, options in fieldsets:
            fields = tuple(
                field
                for field in options.get("fields", ())
                if field not in restricted_fields
            )

            if fields:
                updated_fieldsets.append(
                    (name, {**options, "fields": fields})
                )

        return updated_fieldsets

    def has_view_permission(self, request, obj=None):
        if (
            obj
            and obj.is_superuser
            and not request.user.is_superuser
        ):
            return False

        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if (
            obj
            and obj.is_superuser
            and not request.user.is_superuser
        ):
            return False

        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if (
            obj
            and obj.is_superuser
            and not request.user.is_superuser
        ):
            return False

        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if obj.is_superuser:
            obj.role = User.Role.ADMINISTRATOR

        obj.is_staff = (
            obj.is_superuser
            or obj.role == User.Role.ADMINISTRATOR
        )

        super().save_model(request, obj, form, change)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)
