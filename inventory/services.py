
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.models import (
    InventoryItem,
    InventoryRegistration,
    InventoryTransaction,
)
from receiving.models import DeliveryReceiptItem


@transaction.atomic
def register_accepted_receipt_item(
    *,
    user,
    receipt_item_id,
    inventory_item_id=None,
    new_item_data=None,
):
    """
    Register an accepted delivery receipt item into inventory.

    This service is only for accepted receipt items that do not
    yet have an inventory item linked to them.

    Existing linked receipt items are already added to stock by
    the receiving service and must not be registered again here.
    """

    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("An active authenticated user is required.")

    if not user.has_perm("inventory.add_inventoryregistration"):
        raise PermissionDenied(
            "You do not have permission to register accepted inventory."
        )

    if inventory_item_id and new_item_data:
        raise ValidationError(
            "Choose an existing inventory item OR create a new item, not both."
        )

    if not inventory_item_id and not new_item_data:
        raise ValidationError(
            "Select an inventory item or provide new item details."
        )

    receipt_item = (
        DeliveryReceiptItem.objects
        .select_for_update()
        .select_related(
            "receipt",
            "purchase_order_item",
            "purchase_order_item__purchase_order",
        )
        .get(pk=receipt_item_id)
    )

    if receipt_item.accepted_quantity <= Decimal("0"):
        raise ValidationError(
            "Only receipt items with accepted quantities can be registered."
        )

    if receipt_item.inventory_item_id:
        raise ValidationError(
            "This receipt item already has an inventory item linked."
        )

    if receipt_item.registration_status != (
        DeliveryReceiptItem.RegistrationStatus.AWAITING_ITEM_SETUP
    ):
        raise ValidationError(
            "This receipt item is not awaiting inventory item setup."
        )

    if receipt_item.registered_quantity > Decimal("0"):
        raise ValidationError(
            "This receipt item already has a registered quantity."
        )

    if InventoryRegistration.objects.filter(
        receipt_item=receipt_item
    ).exists():
        raise ValidationError(
            "An inventory registration already exists for this receipt item."
        )

    accepted_quantity = receipt_item.accepted_quantity
    purchase_order = receipt_item.receipt.purchase_order

    item_created = False

    if inventory_item_id:
        inventory_item = (
            InventoryItem.objects
            .select_for_update()
            .filter(pk=inventory_item_id, is_active=True)
            .first()
        )

        if inventory_item is None:
            raise ValidationError(
                "The selected inventory item does not exist or is inactive."
            )

    else:
        data = dict(new_item_data)

        if "quantity_on_hand" in data:
            raise ValidationError(
                "New inventory items must start with zero stock."
            )

        if "quantity_reserved" in data:
            raise ValidationError(
                "Reserved quantity cannot be supplied during registration."
            )

        inventory_item = InventoryItem.objects.create(
            **data,
            quantity_on_hand=Decimal("0"),
            quantity_reserved=Decimal("0"),
        )
        item_created = True

    inventory_item.quantity_on_hand += accepted_quantity
    inventory_item.save()

    ledger_entry = InventoryTransaction.record(
        inventory_item=inventory_item,
        transaction_type=InventoryTransaction.TransactionType.RECEIPT,
        on_hand_change=accepted_quantity,
        reference=receipt_item.receipt.receipt_number,
        related_reference=purchase_order.po_number,
        remarks=(
            f"Inventory registered from delivery receipt "
            f"{receipt_item.receipt.receipt_number} "
            f"for purchase order {purchase_order.po_number}."
        ),
        created_by=user,
    )

    registration = InventoryRegistration.objects.create(
        receipt_item=receipt_item,
        inventory_item=inventory_item,
        ledger_entry=ledger_entry,
        quantity=accepted_quantity,
        item_created=item_created,
        registered_by=user,
    )

    # DeliveryReceiptItem is immutable after creation.
    # This controlled queryset update links the inventory item
    # after validation, without changing its original delivery quantities.
    updated = DeliveryReceiptItem.objects.filter(
        pk=receipt_item.pk,
        inventory_item__isnull=True,
        registration_status=(
            DeliveryReceiptItem.RegistrationStatus.AWAITING_ITEM_SETUP
        ),
        registered_quantity=Decimal("0"),
    ).update(
        inventory_item=inventory_item,
        registration_status=(
            DeliveryReceiptItem.RegistrationStatus.REGISTERED
        ),
        registered_quantity=accepted_quantity,
    )

    if updated != 1:
        raise ValidationError(
            "The receipt item changed during registration. Please try again."
        )

    return registration
