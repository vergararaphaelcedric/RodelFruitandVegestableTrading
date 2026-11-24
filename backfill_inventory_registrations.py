
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import InventoryTransaction, InventoryRegistration
from receiving.models import DeliveryReceiptItem


def backfill():
    records = [
        (1, 27),  # DR-0001
        (3, 28),  # DR-0003
    ]

    with transaction.atomic():
        for receipt_item_id, ledger_id in records:
            receipt_item = DeliveryReceiptItem.objects.select_related(
                "receipt", "inventory_item"
            ).get(pk=receipt_item_id)

            ledger = InventoryTransaction.objects.get(pk=ledger_id)

            if receipt_item.accepted_quantity <= 0:
                raise ValueError("Accepted quantity must be greater than zero.")

            if receipt_item.inventory_item_id != ledger.inventory_item_id:
                raise ValueError("Inventory item mismatch.")

            if receipt_item.receipt.receipt_number != ledger.reference:
                raise ValueError("Receipt reference mismatch.")

            if receipt_item.accepted_quantity != ledger.on_hand_change:
                raise ValueError("Accepted quantity mismatch.")

            registration, created = InventoryRegistration.objects.get_or_create(
                receipt_item=receipt_item,
                defaults={
                    "inventory_item": receipt_item.inventory_item,
                    "ledger_entry": ledger,
                    "quantity": receipt_item.accepted_quantity,
                    "item_created": False,
                    "registered_by": receipt_item.receipt.received_by,
                },
            )

            if not created and (
                registration.ledger_entry_id != ledger.id
                or registration.quantity != receipt_item.accepted_quantity
            ):
                raise ValueError("Existing registration does not match.")

            print(
                "Created:" if created else "Already exists:",
                registration,
            )


if __name__ == "__main__":
    backfill()
