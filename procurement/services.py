
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from requisitions.models import Requisition, StockReservation

from .models import PurchaseRequest, PurchaseRequestItem


@transaction.atomic
def create_purchase_request(requisition, user=None):
    """
    Create one purchase request containing all outstanding shortages
    for an approved or partially fulfilled requisition.
    """

    req = Requisition.objects.select_for_update().get(
        pk=requisition.pk
    )

    allowed_statuses = {
        Requisition.Status.APPROVED,
        Requisition.Status.PARTIALLY_FULFILLED,
    }

    if req.status not in allowed_statuses:
        return None

    purchase_lines = []

    for line in req.items.select_related("inventory_item").order_by("id"):
        # Do not create duplicate purchase request lines.
        if PurchaseRequestItem.objects.filter(
            requisition_item=line
        ).exists():
            continue

        outstanding = line.quantity_outstanding

        if outstanding <= Decimal("0"):
            continue

        reserved = Decimal("0")
        inventory_item = line.inventory_item

        if inventory_item:
            try:
                reservation = line.stock_reservation
            except StockReservation.DoesNotExist:
                # Do not guess the available stock.
                continue

            reserved = reservation.quantity_reserved

        shortage = outstanding - reserved

        if shortage <= Decimal("0"):
            continue

        item_description = line.item_description

        if not item_description and inventory_item:
            item_description = inventory_item.name

        unit_of_measure = line.unit_of_measure

        if not unit_of_measure and inventory_item:
            unit_of_measure = inventory_item.unit_of_measure

        if not item_description or not unit_of_measure:
            continue

        purchase_lines.append({
            "requisition_item": line,
            "inventory_item": inventory_item,
            "item_description": item_description,
            "unit_of_measure": unit_of_measure,
            "quantity_requested": outstanding,
            "quantity_reserved": reserved,
            "quantity_shortage": shortage,
        })
    if not purchase_lines:
        return None

    purchase_request = PurchaseRequest.objects.create(
        requisition=req,
        created_by=user,
        status=PurchaseRequest.Status.PENDING,
    )

    PurchaseRequestItem.objects.bulk_create([
        PurchaseRequestItem(
            purchase_request=purchase_request,
            **line,
        )
        for line in purchase_lines
    ])

    return purchase_request


@transaction.atomic
def cancel_for_requisition(requisition, reason="Requisition cancelled"):
    """
    Cancel pending purchase requests for a cancelled requisition.
    Ordered and received requests remain unchanged.
    """

    req = Requisition.objects.select_for_update().get(
        pk=requisition.pk
    )

    pending_requests = PurchaseRequest.objects.select_for_update().filter(
        requisition=req,
        status=PurchaseRequest.Status.PENDING,
    )

    return pending_requests.update(
        status=PurchaseRequest.Status.CANCELLED,
        notes=reason,
        updated_at=timezone.now(),
    )
