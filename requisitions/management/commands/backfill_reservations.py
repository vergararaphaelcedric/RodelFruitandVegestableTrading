
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import InventoryItem, InventoryTransaction
from requisitions.models import Requisition
from requisitions.stock import reserve_for_requisition


class Command(BaseCommand):
    help = (
        "Backfill opening inventory transactions and missing "
        "reservations for approved requisitions. Safe to re-run."
    )

    def handle(self, *args, **options):
        opening_created = 0
        zero_balance_skipped = 0
        reservations_processed = 0

        # --------------------------------------------------
        # 1. Record opening balances for items without ledger
        # --------------------------------------------------

        item_ids = (
            InventoryItem.objects
            .filter(transactions__isnull=True)
            .order_by("pk")
            .values_list("pk", flat=True)
            .distinct()
        )

        for item_id in item_ids:
            with transaction.atomic():
                item = (
                    InventoryItem.objects
                    .select_for_update()
                    .get(pk=item_id)
                )

                # Recheck after acquiring the lock.
                if item.transactions.exists():
                    continue

                if (
                    item.quantity_on_hand == 0
                    and item.quantity_reserved == 0
                ):
                    zero_balance_skipped += 1
                    continue

                InventoryTransaction.record(
                    inventory_item=item,
                    transaction_type=(
                        InventoryTransaction.TransactionType.ADJUSTMENT
                    ),
                    on_hand_change=item.quantity_on_hand,
                    reserved_change=item.quantity_reserved,
                    reference=f"OPENING-{item.item_code}",
                    remarks=(
                        "Opening balance recorded during "
                        "reservation backfill."
                    ),
                )

                opening_created += 1

        # --------------------------------------------------
        # 2. Process approved requisitions
        # --------------------------------------------------

        approved_requisitions = (
            Requisition.objects
            .filter(
                status__in=[
                    Requisition.Status.APPROVED,
                    Requisition.Status.PARTIALLY_FULFILLED,
                ]
            )
            .order_by("pk")
        )

        for requisition in approved_requisitions:
            reserve_for_requisition(requisition)
            reservations_processed += 1

        # --------------------------------------------------
        # 3. Display results
        # --------------------------------------------------

        self.stdout.write(
            self.style.SUCCESS(
                "Reservation backfill completed successfully."
            )
        )

        self.stdout.write(
            f"Opening balance transactions created: {opening_created}"
        )

        self.stdout.write(
            f"Zero-balance items skipped: {zero_balance_skipped}"
        )

        self.stdout.write(
            f"Approved requisitions processed: {reservations_processed}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                "The command can safely be run again."
            )
        )
