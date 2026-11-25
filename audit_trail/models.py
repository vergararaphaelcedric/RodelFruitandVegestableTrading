
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Records security and business events.
    Audit records are intended to be append-only.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    actor_username = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    category = models.CharField(max_length=50)
    action = models.CharField(max_length=100)
    outcome = models.CharField(max_length=30, default="SUCCESS")

    description = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    user_agent = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["category", "created_at"],
                name="audit_category_date_idx",
            ),
            models.Index(
                fields=["action", "created_at"],
                name="audit_action_date_idx",
            ),
            models.Index(
                fields=["outcome", "created_at"],
                name="audit_outcome_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.created_at} | "
            f"{self.actor_username or 'System'} | "
            f"{self.action} | {self.outcome}"
        )

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Audit logs cannot be modified.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit logs cannot be deleted.")
