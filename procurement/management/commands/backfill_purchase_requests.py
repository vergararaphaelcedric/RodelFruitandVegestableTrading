
from django.core.management.base import BaseCommand

from requisitions.models import Requisition
from procurement.models import PurchaseRequest
from procurement.services import create_purchase_request


class Command(BaseCommand):
    help = (
        "Backfill missing purchase requests for approved "
        "requisitions with outstanding shortages. Safe to re-run."
    )

    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0

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
            purchase_request = create_purchase_request(requisition)

            if purchase_request:
                created_count += 1

                self.stdout.write(
                    f"Created {purchase_request.request_number} "
                    f"for {requisition.requisition_number}."
                )
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Purchase Request backfill completed successfully."
            )
        )

        self.stdout.write(
            f"Purchase Requests created: {created_count}"
        )

        self.stdout.write(
            f"Requisitions skipped: {skipped_count}"
        )

        self.stdout.write(
            self.style.SUCCESS(
                "The command can safely be run again."
            )
        )

