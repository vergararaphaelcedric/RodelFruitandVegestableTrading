
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.models import InventoryItem, InventoryTransaction

from .models import Requisition, RequisitionItem, StockReservation


ZERO = Decimal("0")


def reserve_for_requisition(requisition, user=None):
    """
    Reserve available inventory for every outstanding requisition line.

    Approval is allowed even when stock is insufficient.
    Existing reservations are not duplicated.
    """

    with transaction.atomic():
        req = Requisition.objects.select_for_update().get(
            pk=requisition.pk
        )

        if req.status not in {
            Requisition.Status.APPROVED,
            Requisition.Status.PARTIALLY_FULFILLED,
        }:
            raise ValidationError(
                "Stock can only be reserved for approved requisitions."
            )

        lines = list(
            RequisitionItem.objects
            .filter(requisition=req)
            .order_by("inventory_item_id", "pk")
        )

        existing_line_ids = set(
            StockReservation.objects.filter(
                requisition_item__requisition=req
            ).values_list("requisition_item_id", flat=True)
        )

        item_ids = sorted({
            line.inventory_item_id
            for line in lines
            if line.inventory_item_id
            and line.pk not in existing_line_ids
        })

        inventory_items = list(
            InventoryItem.objects
            .select_for_update()
            .filter(pk__in=item_ids)
            .order_by("pk")
        )

        items_by_id = {
            item.pk: item for item in inventory_items
        }

        for line in lines:
            if line.pk in existing_line_ids:
                continue

            if not line.inventory_item_id:
                continue

            item = items_by_id.get(line.inventory_item_id)

            if item is None:
                continue

            outstanding = line.quantity_outstanding

            if outstanding <= ZERO:
                continue

            available = item.quantity_available
            reserved = min(outstanding, max(available, ZERO))

            StockReservation.objects.create(
                requisition_item=line,
                inventory_item=item,
                quantity_requested=outstanding,
                quantity_reserved=reserved,
                status=StockReservation.Status.ACTIVE,
                reserved_by=user,
            )

            if reserved > ZERO:
                item.quantity_reserved += reserved

                item.save(
                    update_fields=[
                        "quantity_reserved",
                        "updated_at",
                    ]
                )

                InventoryTransaction.record(
                    inventory_item=item,
                    transaction_type=(
                        InventoryTransaction.TransactionType.RESERVE
                    ),
                    reserved_change=reserved,
                    reference=req.requisition_number,
                    remarks=(
                        f"Stock reserved for "
                        f"{req.requisition_number}."
                    ),
                    created_by=user,
                )

        return stock_check(req)


def release_for_requisition(requisition, user=None):
    """
    Release all active stock reservations for a requisition.
    Released reservation records remain in the database.
    """

    with transaction.atomic():
        req = Requisition.objects.select_for_update().get(
            pk=requisition.pk
        )

        reservations = list(
            StockReservation.objects
            .filter(
                requisition_item__requisition=req,
                status=StockReservation.Status.ACTIVE,
            )
            .order_by("inventory_item_id", "pk")
        )

        item_ids = sorted({
            reservation.inventory_item_id
            for reservation in reservations
        })

        inventory_items = list(
            InventoryItem.objects
            .select_for_update()
            .filter(pk__in=item_ids)
            .order_by("pk")
        )

        items_by_id = {
            item.pk: item for item in inventory_items
        }

        for reservation in reservations:
            item = items_by_id.get(reservation.inventory_item_id)

            if item is None:
                raise ValidationError(
                    "An inventory item for a reservation was not found."
                )

            amount = reservation.quantity_reserved

            if amount > item.quantity_reserved:
                raise ValidationError(
                    "Reserved stock is inconsistent. "
                    "The reservation cannot be released safely."
                )

            if amount > ZERO:
                item.quantity_reserved -= amount

                item.save(
                    update_fields=[
                        "quantity_reserved",
                        "updated_at",
                    ]
                )

                InventoryTransaction.record(
                    inventory_item=item,
                    transaction_type=(
                        InventoryTransaction.TransactionType.RELEASE
                    ),
                    reserved_change=-amount,
                    reference=req.requisition_number,
                    remarks=(
                        f"Stock reservation released for "
                        f"{req.requisition_number}."
                    ),
                    created_by=user,
                )

            reservation.status = StockReservation.Status.RELEASED
            reservation.released_at = timezone.now()

            reservation.save(
                update_fields=["status", "released_at"]
            )

        return len(reservations)


def stock_check(requisition):
    """
    Return a stock availability summary.

    Submitted requisitions receive a live preview.
    Approved requisitions display their recorded reservations.
    """

    req = requisition

    lines = list(
        RequisitionItem.objects
        .filter(requisition=req)
        .order_by("pk")
    )

    reservations = {
        reservation.requisition_item_id: reservation
        for reservation in StockReservation.objects.filter(
            requisition_item__requisition=req
        )
    }

    item_ids = sorted({
        line.inventory_item_id
        for line in lines
        if line.inventory_item_id
    })

    fresh_items = InventoryItem.objects.in_bulk(item_ids)

    is_preview = req.status == Requisition.Status.SUBMITTED

    rows = []

    for line in lines:
        item = fresh_items.get(line.inventory_item_id)

        if item is None:
            rows.append({
                "line": line,
                "item": None,
                "requested": line.quantity_outstanding,
                "available": None,
                "reserved": ZERO,
                "shortage": line.quantity_outstanding,
                "outcome": "not_inventory",
            })
            continue

        reservation = reservations.get(line.pk)

        if is_preview:
            available = item.quantity_available
            requested = line.quantity_outstanding
            reserved = min(
                requested,
                max(available, ZERO),
            )
            shortage = requested - reserved

        elif reservation:
            requested = reservation.quantity_requested
            reserved = (
                reservation.quantity_reserved
                if reservation.status == StockReservation.Status.ACTIVE
                else ZERO
            )
            shortage = requested - reserved
            available = item.quantity_available

        else:
            rows.append({
                "line": line,
                "item": item,
                "requested": line.quantity_outstanding,
                "available": item.quantity_available,
                "reserved": ZERO,
                "shortage": line.quantity_outstanding,
                "outcome": "unchecked",
            })
            continue

        if reserved == ZERO:
            outcome = "none"
        elif shortage > ZERO:
            outcome = "partial"
        else:
            outcome = "sufficient"

        rows.append({
            "line": line,
            "item": item,
            "requested": requested,
            "available": available,
            "reserved": reserved,
            "shortage": shortage,
            "outcome": outcome,
        })

    counts = {
        "sufficient": 0,
        "partial": 0,
        "none": 0,
        "not_inventory": 0,
        "unchecked": 0,
    }

    for row in rows:
        counts[row["outcome"]] += 1

    if counts["unchecked"]:
        overall = "unchecked"
    elif counts["not_inventory"] == len(rows) and rows:
        overall = "not_inventory"
    elif counts["partial"] or counts["none"] or counts["not_inventory"]:
        overall = "shortage"
    else:
        overall = "sufficient"

    return {
        "requisition": req,
        "rows": rows,
        "counts": counts,
        "overall": overall,
        "is_preview": is_preview,
    }


def describe(check):
    """Create a concise approval message describing stock availability."""

    counts = check["counts"]

    if check["overall"] == "unchecked":
        return (
            "Approval recorded, but some stock reservations "
            "have not been checked."
        )

    if check["overall"] == "sufficient":
        return "Approved successfully. All inventory items are covered."

    shortage_lines = []

    for row in check["rows"]:
        if row["shortage"] > ZERO:
            name = (
                row["item"].name
                if row["item"]
                else row["line"].description
            )

            shortage_lines.append(
                f"{name}: shortage of {row['shortage']}"
            )

    if shortage_lines:
        return (
            "Approved successfully, but some items need purchasing: "
            + "; ".join(shortage_lines)
        )

    return (
        "Approved successfully. "
        f"Items requiring attention: {counts['not_inventory']}."
    )
