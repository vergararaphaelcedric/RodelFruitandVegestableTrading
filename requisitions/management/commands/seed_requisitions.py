
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Department, User
from inventory.models import InventoryItem
from requisitions.models import (
    Requisition,
    RequisitionItem,
    StatusHistory,
)
from requisitions.services import (
    change_status,
    decide_requisition,
)


# Development only. Change before using this system beyond local testing.
DEV_PASSWORD = "ChangeMe123!"


class Command(BaseCommand):
    help = (
        "Create sample users and requisitions with "
        "approval/status history (safe to re-run)."
    )

    def _user(self, username, first, last, dept, **extra):
        user = User.objects.filter(username=username).first()

        if not user:
            user = User.objects.create_user(
                username,
                password=DEV_PASSWORD,
                first_name=first,
                last_name=last,
                department=dept,
                **extra,
            )

        return user

    @transaction.atomic
    def handle(self, *args, **options):
        # Create or retrieve Finance department.
        dept, _ = Department.objects.get_or_create(
            name="Finance",
            defaults={"code": "FIN"},
        )

        # Get approval permission.
        approve = Permission.objects.get(
            content_type__app_label="requisitions",
            codename="approve_requisition",
        )

        # Get relevant viewing permissions.
        view_perms = Permission.objects.filter(
            codename__startswith="view_",
            content_type__app_label__in=[
                "accounts",
                "inventory",
                "requisitions",
            ],
        )

        # Create approver group.
        group, _ = Group.objects.get_or_create(
            name="Requisition Approvers"
        )

        group.permissions.add(approve, *view_perms)

        # Create sample users.
        requester = self._user(
            "juan.requester",
            "Juan",
            "Dela Cruz",
            dept,
        )

        manager = self._user(
            "maria.manager",
            "Maria",
            "Santos",
            dept,
            is_staff=True,
        )

        manager.groups.add(group)

        # Refresh manager permissions.
        manager = User.objects.get(pk=manager.pk)

        # Find sample inventory item.
        paper = InventoryItem.objects.filter(
            item_code="OFF-0001"
        ).first()

        # Sample requisitions.
        samples = [
            (
                "[SAMPLE] Draft - desk supplies",
                "draft",
                None,
            ),
            (
                "[SAMPLE] Awaiting approval - printer toner",
                "submitted",
                None,
            ),
            (
                "[SAMPLE] Approved - bond paper and folders",
                "approved",
                "Within budget.",
            ),
            (
                "[SAMPLE] Rejected - premium monitors",
                "rejected",
                "Over budget. Please request standard monitors.",
            ),
        ]

        created_count = 0

        for purpose, final, remarks in samples:
            req, created = Requisition.objects.get_or_create(
                purpose=purpose,
                defaults={
                    "requested_by": requester,
                    "department": dept,
                },
            )

            if not created:
                continue

            created_count += 1

            # Record initial Draft status.
            StatusHistory.objects.create(
                requisition=req,
                previous_status="",
                new_status=req.status,
                changed_by=requester,
                remarks="Requisition created.",
            )

            # Add sample inventory item to approved request.
            if paper and final == "approved":
                RequisitionItem.objects.create(
                    requisition=req,
                    inventory_item=paper,
                    quantity_requested=Decimal("10"),
                )

            # Add a sample custom item.
            RequisitionItem.objects.create(
                requisition=req,
                item_description="Sample requested item",
                unit_of_measure="pc",
                quantity_requested=Decimal("2"),
            )

            # Submit requisitions when needed.
            if final != "draft":
                change_status(
                    req,
                    Requisition.Status.SUBMITTED,
                    requester,
                )

            # Approve or reject when needed.
            if final in ("approved", "rejected"):
                decide_requisition(
                    req,
                    manager,
                    final,
                    remarks,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{created_count} sample requisitions created. "
                "Users: juan.requester (requester), "
                "maria.manager (approver). "
                f"Password for both: {DEV_PASSWORD}"
            )
        )
