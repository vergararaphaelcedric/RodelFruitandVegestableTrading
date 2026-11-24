
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from procurement.services import (
    cancel_for_requisition,
    create_purchase_request,
)

from .models import ApprovalHistory, Requisition, StatusHistory
from .stock import release_for_requisition, reserve_for_requisition


S = Requisition.Status


ALLOWED_TRANSITIONS = {
    S.DRAFT: {S.SUBMITTED, S.CANCELLED},
    S.SUBMITTED: {S.APPROVED, S.REJECTED, S.CANCELLED},
    S.APPROVED: {S.PARTIALLY_FULFILLED, S.FULFILLED, S.CANCELLED},
    S.PARTIALLY_FULFILLED: {S.FULFILLED, S.CANCELLED},
    S.REJECTED: set(),
    S.FULFILLED: set(),
    S.CANCELLED: set(),
}


USER_SETTABLE = {
    S.SUBMITTED,
    S.CANCELLED,
}


def _apply_status(req, new_status, user, remarks):
    previous = req.status

    if new_status not in ALLOWED_TRANSITIONS.get(previous, set()):
        raise ValidationError(
            f"Cannot change status from '{previous}' to '{new_status}'."
        )

    req.status = new_status
    req.save(update_fields=["status", "updated_at"])

    return StatusHistory.objects.create(
        requisition=req,
        previous_status=previous,
        new_status=new_status,
        changed_by=user,
        remarks=remarks,
    )


def change_status(requisition, new_status, user, remarks=""):
    """Submit or cancel a requisition, and record the change."""

    if new_status not in USER_SETTABLE:
        raise PermissionDenied(
            "This status cannot be set directly. "
            "Use decide_requisition() to approve or reject."
        )

    with transaction.atomic():
        req = Requisition.objects.select_for_update().get(
            pk=requisition.pk
        )

        is_owner = user.pk == req.requested_by_id

        can_approve = user.is_active and user.has_perm(
            "requisitions.approve_requisition"
        )

        if new_status == S.SUBMITTED and not is_owner:
            raise PermissionDenied(
                "Only the requester can submit a requisition."
            )

        if new_status == S.CANCELLED and not (is_owner or can_approve):
            raise PermissionDenied(
                "You cannot cancel this requisition."
            )

        history = _apply_status(
            req,
            new_status,
            user,
            remarks,
        )

        if new_status == S.CANCELLED:
            release_for_requisition(req, user)

            cancel_for_requisition(
                req,
                reason=remarks or "Requisition cancelled",
            )

    requisition.status = req.status

    return history


def decide_requisition(requisition, approver, decision, remarks=""):
    """Approve or reject a submitted requisition."""

    remarks = (remarks or "").strip()

    if decision not in ApprovalHistory.Decision.values:
        raise ValidationError(
            "Decision must be 'approved' or 'rejected'."
        )

    with transaction.atomic():
        req = Requisition.objects.select_for_update().get(
            pk=requisition.pk
        )

        approval = ApprovalHistory(
            requisition=req,
            approver=approver,
            decision=decision,
            remarks=remarks,
            previous_status=req.status,
            new_status=decision,
        )

        approval.check_authorized()

        if req.status != S.SUBMITTED:
            raise ValidationError(
                "Only submitted requisitions can be approved or rejected."
            )

        approval.full_clean()

        approval.status_history = _apply_status(
            req,
            decision,
            approver,
            remarks,
        )

        approval.save()

        if decision == ApprovalHistory.Decision.APPROVED:
            reserve_for_requisition(req, approver)

            create_purchase_request(req, approver)

    requisition.status = req.status

    return approval
