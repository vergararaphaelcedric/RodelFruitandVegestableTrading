from django.db.models import Count, Exists, OuterRef, Subquery

from .models import ApprovalHistory, Requisition, StatusHistory


S = Requisition.Status


def reviewable_requisitions(user):
    """
    Requisitions that were submitted and do not belong to the manager.
    Drafts and a manager's own requests are excluded.
    """

    submitted = StatusHistory.objects.filter(
        requisition=OuterRef("pk"),
        new_status=S.SUBMITTED,
    )

    return (
        Requisition.objects
        .annotate(was_submitted=Exists(submitted))
        .filter(was_submitted=True)
        .exclude(requested_by=user)
        .select_related("requested_by", "department")
    )


def pending_for(user):
    """Requisitions currently awaiting a manager's decision."""

    return reviewable_requisitions(user).filter(
        status=S.SUBMITTED
    )


def with_list_annotations(queryset):
    """Add item count, submission date, and latest decision date."""

    submitted_at = (
        StatusHistory.objects
        .filter(
            requisition=OuterRef("pk"),
            new_status=S.SUBMITTED,
        )
        .order_by("-changed_at", "-id")
        .values("changed_at")[:1]
    )

    decided_at = (
        ApprovalHistory.objects
        .filter(requisition=OuterRef("pk"))
        .order_by("-acted_at", "-id")
        .values("acted_at")[:1]
    )

    return queryset.annotate(
        item_total=Count("items", distinct=True),
        submitted_at=Subquery(submitted_at),
        decided_at=Subquery(decided_at),
    )