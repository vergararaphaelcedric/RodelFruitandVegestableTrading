from audit_trail.models import AuditLog


SENSITIVE_KEYS = {
    "password",
    "user_password",
    "new_password",
    "old_password",
    "password1",
    "password2",
    "token",
    "access_token",
    "refresh_token",
    "secret",
}


def _clean_details(value):
    """
    Remove sensitive values before storing audit details.
    """
    if isinstance(value, dict):
        cleaned = {}

        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = _clean_details(item)

        return cleaned

    if isinstance(value, (list, tuple)):
        return [_clean_details(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def log_event(
    action,
    category="SYSTEM",
    outcome="SUCCESS",
    description="",
    request=None,
    actor=None,
    details=None,
):
    """
    Create one audit log entry.

    Example:
        log_event(
            action="USER_CREATED",
            category="USER",
            description="A user account was created.",
            request=request,
            details={"created_user_id": user.pk},
        )
    """

    if actor is None and request is not None:
        request_user = getattr(request, "user", None)

        if request_user is not None and request_user.is_authenticated:
            actor = request_user

    actor_username = ""

    if actor is not None:
        actor_username = getattr(actor, "username", "") or str(actor)

    ip_address = None
    user_agent = ""

    if request is not None:
        ip_address = request.META.get("REMOTE_ADDR")

        user_agent = request.META.get(
            "HTTP_USER_AGENT",
            "",
        )[:1000]

    cleaned_details = _clean_details(details or {})

    if not isinstance(cleaned_details, dict):
        cleaned_details = {"value": cleaned_details}

    return AuditLog.objects.create(
        actor=actor,
        actor_username=actor_username,
        category=category,
        action=action,
        outcome=outcome,
        description=description,
        details=cleaned_details,
        ip_address=ip_address,
        user_agent=user_agent,
    )