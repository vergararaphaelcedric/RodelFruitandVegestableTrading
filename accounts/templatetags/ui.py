from django import template

register = template.Library()


@register.filter
def status_class(value):
    """Return a Bootstrap-compatible color class for a status."""
    status = str(value or "").strip().lower()

    if status in {"approved", "completed", "received", "active", "paid"}:
        return "success"

    if status in {"pending", "submitted", "processing", "partial"}:
        return "warning"

    if status in {"rejected", "cancelled", "canceled", "inactive", "failed"}:
        return "danger"

    if status in {"draft", "available", "unpaid"}:
        return "secondary"

    return "info"
