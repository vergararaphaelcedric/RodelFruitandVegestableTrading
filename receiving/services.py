
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum

from inventory.models import (
    InventoryItem,
    InventoryTransaction,
    InventoryRegistration,
)
from procurement.models import PurchaseOrder, PurchaseRequest

from .models import (
    DeliveryReceipt,
    DeliveryReceiptItem,
    DeliveryDiscrepancy,
)


def _to_decimal(value, field_name):
    """Convert submitted quantities into valid Decimal values."""
    try:
        quantity = Decimal(
            str(value if value not in (None, "") else "0")
        )
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({
            field_name: "Enter a valid quantity."
        })

    if not quantity.is_finite():
        raise ValidationError({
            field_name: "Enter a valid finite quantity."
        })

    if quantity < 0:
        raise ValidationError({
            field_name: "Quantity cannot be negative."
        })

    return quantity


def _accepted_quantity_for(po_item):
    """Return the total accepted quantity recorded for a PO line."""
    result = DeliveryReceiptItem.objects.filter(
        purchase_order_item=po_item
    ).aggregate(
        total=Sum("accepted_quantity")
    )

    return result["total"] or Decimal("0")


def _update_purchase_request_status(purchase_request):
    """
    Mark a Purchase Request as received only when every PO line
    has been fully accepted.
    """
    purchase_request = (
        PurchaseRequest.objects.select_for_update()
        .get(pk=purchase_request.pk)
    )

    if purchase_request.status != PurchaseRequest.Status.ORDERED:
        return

    purchase_orders = (
        purchase_request.purchase_orders.prefetch_related("items")
    )

    for purchase_order in purchase_orders:
        for po_item in purchase_order.items.all():
            accepted = _accepted_quantity_for(po_item)

            if accepted < po_item.quantity:
                return

    purchase_request.status = PurchaseRequest.Status.RECEIVED
    purchase_request.save(update_fields=["status", "updated_at"])


@transaction.atomic
def record_delivery(
    *,
    user,
    purchase_order_id,
    delivery_note_number="",
    remarks="",
    items,
):
    """
    Record a delivery against an issued Purchase Order.

    Each item dictionary must contain:
        purchase_order_item_id
        delivered_quantity
        accepted_quantity
        damaged_quantity
        incorrect_quantity

    Optional discrepancy descriptions:
        damaged_description
        incorrect_description

    Only accepted quantities linked to an InventoryItem
    are added to inventory.
    """

    required_permissions = [
        "receiving.add_deliveryreceipt",
        "receiving.add_deliveryreceiptitem",
        "receiving.add_deliverydiscrepancy",
    ]

    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied(
            "An active signed-in user is required."
        )

    if not all(
        user.has_perm(permission)
        for permission in required_permissions
    ):
        raise PermissionDenied(
            "You do not have permission to record deliveries."
        )

    if not items:
        raise ValidationError(
            "Add at least one delivered purchase order item."
        )

    purchase_order = (
        PurchaseOrder.objects.select_for_update()
        .select_related("purchase_request", "supplier")
        .get(pk=purchase_order_id)
    )

    if purchase_order.status != PurchaseOrder.Status.ISSUED:
        raise ValidationError(
            "Only issued purchase orders can receive deliveries."
        )

    po_items = {
       po_item.pk: po_item
       for po_item in (
          purchase_order.items
          .select_for_update(of=("self",))
          .select_related("inventory_item")
        )
}
    prepared_items = []
    seen_item_ids = set()

    total_accepted = Decimal("0")
    total_discrepancies = Decimal("0")

    for submitted in items:
        try:
            po_item_id = int(
                submitted["purchase_order_item_id"]
            )
        except (KeyError, TypeError, ValueError):
            raise ValidationError(
                "Every delivery line must identify a purchase order item."
            )

        if po_item_id in seen_item_ids:
            raise ValidationError(
                "A purchase order item cannot appear twice in one receipt."
            )

        seen_item_ids.add(po_item_id)

        po_item = po_items.get(po_item_id)

        if po_item is None:
            raise ValidationError(
                "A submitted item does not belong to this purchase order."
            )

        delivered = _to_decimal(
            submitted.get("delivered_quantity"),
            "delivered_quantity",
        )

        accepted = _to_decimal(
            submitted.get("accepted_quantity"),
            "accepted_quantity",
        )

        damaged = _to_decimal(
            submitted.get("damaged_quantity"),
            "damaged_quantity",
        )

        incorrect = _to_decimal(
            submitted.get("incorrect_quantity"),
            "incorrect_quantity",
        )

        # If nothing was delivered, every quantity must be zero.
        if delivered == 0:
            if accepted != 0 or damaged != 0 or incorrect != 0:
                raise ValidationError(
                    f"Quantities for {po_item.item_description} "
                    "must all be zero when nothing was delivered."
                )

            continue

        # All delivered quantities must be accounted for.
        if accepted + damaged + incorrect != delivered:
            raise ValidationError(
                f"Quantities for {po_item.item_description} must balance: "
                "delivered = accepted + damaged + incorrect."
            )

        already_accepted = _accepted_quantity_for(po_item)
        outstanding = po_item.quantity - already_accepted

        if delivered > outstanding:
            raise ValidationError(
                f"Delivered quantity for {po_item.item_description} "
                f"exceeds the outstanding quantity of {outstanding}."
            )

        prepared_items.append({
            "po_item": po_item,
            "delivered": delivered,
            "accepted": accepted,
            "damaged": damaged,
            "incorrect": incorrect,
            "damaged_description": (
                submitted.get("damaged_description")
                or submitted.get("description")
                or ""
            ).strip(),
            "incorrect_description": (
                submitted.get("incorrect_description")
                or submitted.get("description")
                or ""
            ).strip(),
        })

        total_accepted += accepted
        total_discrepancies += damaged + incorrect

    if not prepared_items:
        raise ValidationError(
            "Enter a delivered quantity greater than zero."
        )

    # Determine the overall delivery outcome.
    if total_accepted == 0:
        outcome = DeliveryReceipt.Outcome.REJECTED
    elif total_discrepancies == 0:
        outcome = DeliveryReceipt.Outcome.FULLY_ACCEPTED
    else:
        outcome = DeliveryReceipt.Outcome.PARTLY_ACCEPTED

    # Create the delivery receipt.
    receipt = DeliveryReceipt.objects.create(
        purchase_order=purchase_order,
        delivery_note_number=delivery_note_number.strip(),
        received_by=user,
        outcome=outcome,
        remarks=remarks.strip(),
    )

    # Process each delivered purchase order item.
    for data in prepared_items:
        po_item = data["po_item"]
        accepted = data["accepted"]

        inventory_item = po_item.inventory_item

        # Only accepted quantities can enter inventory.
        if inventory_item and accepted > 0:
            inventory_item = (
                InventoryItem.objects.select_for_update()
                .get(pk=inventory_item.pk)
            )

            if not inventory_item.is_active:
                raise ValidationError(
                    f"{inventory_item.name} is inactive and cannot "
                    "receive accepted stock."
                )

            inventory_item.quantity_on_hand += accepted
            inventory_item.save()

            registration_status = (
                DeliveryReceiptItem.RegistrationStatus.REGISTERED
            )

            registered_quantity = accepted

        elif accepted > 0:
            # Accepted items without an inventory record must
            # wait for item setup before becoming available.
            registration_status = (
                DeliveryReceiptItem.RegistrationStatus.AWAITING_ITEM_SETUP
            )

            registered_quantity = Decimal("0")

        else:
            registration_status = (
                DeliveryReceiptItem.RegistrationStatus.NOT_APPLICABLE
            )

            registered_quantity = Decimal("0")

        receipt_item = DeliveryReceiptItem(
            receipt=receipt,
            purchase_order_item=po_item,
            inventory_item=inventory_item,
            delivered_quantity=data["delivered"],
            accepted_quantity=accepted,
            damaged_quantity=data["damaged"],
            incorrect_quantity=data["incorrect"],
            registration_status=registration_status,
            registered_quantity=registered_quantity,
        )

        receipt_item.full_clean()
        receipt_item.save()

              # Record the inventory ledger entry only for accepted stock.
        # The stock quantity was already updated above.
        if inventory_item and accepted > 0:
            ledger_entry = InventoryTransaction.record(
                inventory_item=inventory_item,
                transaction_type=(
                    InventoryTransaction.TransactionType.RECEIPT
                ),
                on_hand_change=accepted,
                reference=receipt.receipt_number,
                related_reference=purchase_order.po_number,
                remarks=(
                    f"Accepted delivery for PO "
                    f"{purchase_order.po_number}."
                ),
                created_by=user,
            )

            # Link the existing stock transaction to its registration.
            # Do not increase inventory quantity again.
            InventoryRegistration.objects.create(
                receipt_item=receipt_item,
                inventory_item=inventory_item,
                ledger_entry=ledger_entry,
                quantity=accepted,
                item_created=False,
                registered_by=user,
            )
        # Record damaged and incorrect items as discrepancies.
        discrepancy_entries = [
            (
                DeliveryDiscrepancy.DiscrepancyType.DAMAGED,
                data["damaged"],
                data["damaged_description"],
            ),
            (
                DeliveryDiscrepancy.DiscrepancyType.INCORRECT,
                data["incorrect"],
                data["incorrect_description"],
            ),
        ]

        for discrepancy_type, quantity, description in discrepancy_entries:
            if quantity <= 0:
                continue

            if not description:
                raise ValidationError(
                    f"Provide a description for the "
                    f"{discrepancy_type} discrepancy."
                )

            discrepancy = DeliveryDiscrepancy(
                receipt_item=receipt_item,
                discrepancy_type=discrepancy_type,
                quantity=quantity,
                description=description,
                reported_by=user,
            )

            discrepancy.full_clean()
            discrepancy.save()

    # Update the Purchase Request only when all ordered quantities
    # have been accepted across its purchase orders.
    _update_purchase_request_status(
        purchase_order.purchase_request
    )

    return receipt
