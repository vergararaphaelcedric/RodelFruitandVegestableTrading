
import uuid
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.models import (
    Asset,
    InventoryItem,
    InventoryRegistration,
    InventoryTransaction,
    ItemAssignment,
)
from receiving.models import DeliveryReceiptItem
from requisitions.models import (
    Requisition,
    RequisitionItem,
    StockReservation,
)


ZERO = Decimal("0")
ONE = Decimal("1.00")


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

    Only accepted receipt items awaiting item setup can be registered.
    Existing linked receipt items must never be registered twice.
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

    if receipt_item.accepted_quantity <= ZERO:
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

    if receipt_item.registered_quantity > ZERO:
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
            quantity_on_hand=ZERO,
            quantity_reserved=ZERO,
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

    # Controlled update because DeliveryReceiptItem is immutable.
    updated = DeliveryReceiptItem.objects.filter(
        pk=receipt_item.pk,
        inventory_item__isnull=True,
        registration_status=(
            DeliveryReceiptItem.RegistrationStatus.AWAITING_ITEM_SETUP
        ),
        registered_quantity=ZERO,
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


def _validate_active_user(user):
    """Ensure the operation is performed by an active authenticated user."""

    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("An active authenticated user is required.")


def _generate_asset_tag():
    """Generate a unique asset tag."""

    return f"AST-{uuid.uuid4().hex[:12].upper()}"


@transaction.atomic
def issue_requisition_item(
    *,
    user,
    requisition_item_id,
    quantity,
    inventory_item_id=None,
    serial_numbers=None,
):
    """
    Issue inventory against an approved requisition item.

    Existing reservations are consumed first and exactly once.
    Additional quantities must come from unreserved stock.
    Durable equipment receives one Asset and one ItemAssignment per unit.
    """

    _validate_active_user(user)

    if not user.has_perm("inventory.issue_items"):
        raise PermissionDenied(
            "You do not have permission to issue inventory items."
        )

    try:
        quantity = Decimal(str(quantity))
    except Exception:
        raise ValidationError("Enter a valid issuance quantity.")

    if not quantity.is_finite() or quantity <= ZERO:
        raise ValidationError(
            "Issuance quantity must be greater than zero."
        )

    line = (
        RequisitionItem.objects
        .select_for_update()
        .select_related("requisition", "requisition__requested_by")
        .get(pk=requisition_item_id)
    )

    requisition = Requisition.objects.select_for_update().get(
        pk=line.requisition_id
    )

    if requisition.status not in {
        Requisition.Status.APPROVED,
        Requisition.Status.PARTIALLY_FULFILLED,
    }:
        raise ValidationError(
            "Only approved requisitions can be fulfilled."
        )

    outstanding = line.quantity_outstanding

    if quantity > outstanding:
        raise ValidationError(
            f"Cannot issue {quantity}. Outstanding quantity is {outstanding}."
        )

    # Normalize the submitted inventory item ID.
    # HTML form values arrive as strings, while model IDs are integers.
    if inventory_item_id in ("", None):
        inventory_item_id = None
    else:
        try:
            inventory_item_id = int(inventory_item_id)
        except (TypeError, ValueError):
            raise ValidationError(
                "Please select a valid inventory item."
            )

        if inventory_item_id <= 0:
            raise ValidationError(
                "Please select a valid inventory item."
            )

    # Resolve and validate the inventory item.
    if inventory_item_id is not None:
        if (
            line.inventory_item_id
            and line.inventory_item_id != inventory_item_id
        ):
            raise ValidationError(
                "The selected item does not match this requisition line."
            )

        inventory_item = (
            InventoryItem.objects
            .select_for_update()
            .filter(
                pk=inventory_item_id,
                is_active=True,
            )
            .first()
        )

        if inventory_item is None:
            raise ValidationError(
                "The selected inventory item does not exist or is inactive."
            )

        # Link a free-text requisition line to the selected inventory item.
        if not line.inventory_item_id:
            line.inventory_item = inventory_item

            RequisitionItem.objects.filter(
                pk=line.pk,
                inventory_item__isnull=True,
            ).update(
                inventory_item=inventory_item,
                item_description=inventory_item.name,
                unit_of_measure=inventory_item.unit_of_measure,
            )

    else:
        if not line.inventory_item_id:
            raise ValidationError(
                "Select an inventory item for this requisition line."
            )

        inventory_item = (
            InventoryItem.objects
            .select_for_update()
            .get(pk=line.inventory_item_id)
        )

    if not inventory_item.is_active:
        raise ValidationError(
            "Inactive inventory items cannot be issued."
        )

    # Validate durable equipment serial numbers.
    if inventory_item.is_durable_equipment:
        if quantity != quantity.to_integral_value():
            raise ValidationError(
                "Durable equipment must be issued in whole units."
            )

        expected_assets = int(quantity)

        if serial_numbers is None:
            serial_numbers = []

        if len(serial_numbers) != expected_assets:
            raise ValidationError(
                f"Provide exactly {expected_assets} serial number(s) "
                "for durable equipment."
            )

        normalized_serials = [
            str(value).strip() for value in serial_numbers
        ]

        if any(not value for value in normalized_serials):
            raise ValidationError(
                "Serial numbers cannot be blank for durable equipment."
            )

        if len(set(normalized_serials)) != len(normalized_serials):
            raise ValidationError(
                "Duplicate serial numbers were provided."
            )

        for serial in normalized_serials:
            if Asset.objects.filter(serial_number=serial).exists():
                raise ValidationError(
                    f"Serial number {serial} is already registered."
                )

    else:
        if serial_numbers:
            raise ValidationError(
                "Serial numbers are only used for durable equipment."
            )

        normalized_serials = []

    # Lock and validate the reservation.
    reservation = (
        StockReservation.objects
        .select_for_update()
        .filter(requisition_item=line)
        .first()
    )

    reserved_to_consume = ZERO

    if reservation:
        if reservation.inventory_item_id != inventory_item.pk:
            raise ValidationError(
                "The reservation belongs to a different inventory item."
            )

        if reservation.status == StockReservation.Status.ACTIVE:
            reserved_to_consume = min(
                quantity,
                reservation.remaining_reserved,
            )

    # Any quantity beyond this requisition's reservation
    # must come from currently unreserved stock.
    unreserved_quantity = quantity - reserved_to_consume

    if unreserved_quantity > inventory_item.quantity_available:
        raise ValidationError(
            "Insufficient unreserved inventory is available for this issuance."
        )

    if quantity > inventory_item.quantity_on_hand:
        raise ValidationError(
            "Issuance quantity exceeds physical inventory."
        )

    if reserved_to_consume > inventory_item.quantity_reserved:
        raise ValidationError(
            "Reserved inventory is inconsistent. Issuance cannot continue."
        )

    # Deduct physical stock and consume the matching reservation.
    inventory_item.quantity_on_hand -= quantity
    inventory_item.quantity_reserved -= reserved_to_consume

    inventory_item.save(
        update_fields=[
            "quantity_on_hand",
            "quantity_reserved",
            "updated_at",
        ]
    )

    if reservation and reserved_to_consume > ZERO:
        reservation.quantity_consumed += reserved_to_consume

        if (
            reservation.quantity_consumed
            > reservation.quantity_reserved
        ):
            raise ValidationError(
                "Issuance would exceed the reserved quantity."
            )

        reservation.save(update_fields=["quantity_consumed"])

    # Record the immutable inventory ledger transaction.
    ledger_entry = InventoryTransaction.record(
        inventory_item=inventory_item,
        transaction_type=InventoryTransaction.TransactionType.ISSUE,
        on_hand_change=-quantity,
        reserved_change=-reserved_to_consume,
        reference=requisition.requisition_number,
        remarks=(
            f"Issued {quantity} of {inventory_item.name} "
            f"for {requisition.requisition_number}."
        ),
        created_by=user,
    )

    # Create employee assignments and individual asset records.
    assignments = []

    if inventory_item.is_durable_equipment:
        for serial in normalized_serials:
            asset = Asset.objects.create(
                asset_tag=_generate_asset_tag(),
                inventory_item=inventory_item,
                serial_number=serial,
                status=Asset.Status.ASSIGNED,
            )

            assignment = ItemAssignment.objects.create(
                requisition_item=line,
                inventory_item=inventory_item,
                asset=asset,
                assigned_to=requisition.requested_by,
                issued_by=user,
                quantity=ONE,
            )

            assignments.append(assignment)

    else:
        assignment = ItemAssignment.objects.create(
            requisition_item=line,
            inventory_item=inventory_item,
            assigned_to=requisition.requested_by,
            issued_by=user,
            quantity=quantity,
        )

        assignments.append(assignment)

    # Update the fulfilled quantity on the requisition line.
    line.quantity_fulfilled += quantity

    line.save(
        update_fields=[
            "quantity_fulfilled",
            "updated_at",
        ]
    )

    # Issued items still require employee acknowledgement.
    requisition.status = Requisition.Status.PARTIALLY_FULFILLED

    requisition.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return {
        "assignments": assignments,
        "inventory_transaction": ledger_entry,
        "inventory_item": inventory_item,
        "issued_quantity": quantity,
        "remaining_quantity": line.quantity_outstanding,
        "requisition": requisition,
    }


@transaction.atomic
def acknowledge_item_assignment(
    *,
    user,
    assignment_id,
    acknowledgement_note="",
):
    """
    Allow an employee to acknowledge an item assigned to them.

    A requisition becomes fulfilled only when every requested quantity
    has been issued and every assignment has been acknowledged.
    """

    _validate_active_user(user)

    if not user.has_perm("inventory.acknowledge_item_assignments"):
        raise PermissionDenied(
            "You do not have permission to acknowledge item assignments."
        )

    assignment = (
        ItemAssignment.objects
        .select_for_update()
        .select_related(
            "assigned_to",
            "requisition_item",
            "requisition_item__requisition",
        )
        .filter(
            pk=assignment_id,
            assigned_to=user,
        )
        .first()
    )

    if assignment is None:
        raise PermissionDenied(
            "This assignment does not belong to your account."
        )

    if assignment.status != ItemAssignment.Status.PENDING_ACKNOWLEDGEMENT:
        raise ValidationError(
            "This assignment has already been acknowledged."
        )

    assignment.status = ItemAssignment.Status.ACKNOWLEDGED
    assignment.acknowledged_at = timezone.now()
    assignment.acknowledgement_note = str(
        acknowledgement_note
    ).strip()

    assignment.save(
        update_fields=[
            "status",
            "acknowledged_at",
            "acknowledgement_note",
        ]
    )

    requisition = assignment.requisition_item.requisition

    all_lines = RequisitionItem.objects.filter(
        requisition=requisition
    )

    all_quantities_issued = all(
        line.quantity_fulfilled >= line.quantity_requested
        for line in all_lines
    )

    has_pending_acknowledgements = ItemAssignment.objects.filter(
        requisition_item__requisition=requisition,
        status=ItemAssignment.Status.PENDING_ACKNOWLEDGEMENT,
    ).exists()

    if all_quantities_issued and not has_pending_acknowledgements:
        requisition.status = Requisition.Status.FULFILLED

        requisition.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

    return assignment
