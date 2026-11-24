
from django.contrib.auth.models import AbstractUser, Group
from django.db import models

from .roles import DASHBOARD_URLS, ROLE_GROUP_NAMES


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class User(AbstractUser):

    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Administrator"
        EMPLOYEE = "employee", "Employee"
        MANAGER = "manager", "Manager"
        INVENTORY_STAFF = "inventory_staff", "Inventory Staff"
        PURCHASING_STAFF = "purchasing_staff", "Purchasing Staff"
        RECEIVING_STAFF = "receiving_staff", "Receiving Staff"

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.EMPLOYEE,
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )

    employee_id = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
    )

    phone = models.CharField(max_length=30, blank=True)

    @property
    def dashboard_url_name(self):
        return DASHBOARD_URLS.get(
            self.role,
            DASHBOARD_URLS["employee"],
        )

    def sync_role_group(self):
        """Keep the user's group membership aligned with their role."""

        if not self.pk:
            return

        group_name = ROLE_GROUP_NAMES.get(self.role)

        if not group_name:
            return

        target_group, _ = Group.objects.get_or_create(
            name=group_name
        )

        # Each user belongs to only their assigned role group.
        # This also removes the old Day 5 "Requisition Approvers" group.
        self.groups.clear()
        self.groups.add(target_group)

    def save(self, *args, **kwargs):
        # New superusers automatically receive the administrator role.
        if self._state.adding and self.is_superuser:
            self.role = self.Role.ADMINISTRATOR

        update_fields = kwargs.get("update_fields")

        should_sync = (
            update_fields is None
            or "role" in update_fields
            or self._state.adding
        )

        super().save(*args, **kwargs)

        if should_sync:
            self.sync_role_group()

    def __str__(self):
        return self.get_full_name() or self.username
