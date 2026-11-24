
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth.models import Permission
from django.test import TestCase

from accounts.models import Department, User
from inventory.models import InventoryItem, InventoryTransaction, ItemCategory
from requisitions.models import (
    ApprovalHistory,
    Requisition,
    RequisitionItem,
    StockReservation,
)
from requisitions.services import decide_requisition
from requisitions.services import change_status, decide_requisition
from requisitions.stock import reserve_for_requisition, stock_check


class RejectionReservationTests(TestCase):

    def setUp(self):
        self.department = Department.objects.create(
            name="Finance",
        )

        self.employee = User.objects.create_user(
            username="stock_test_employee",
            password="TestPassword123!",
            department=self.department,
        )

        self.manager = User.objects.create_user(
            username="stock_test_manager",
            password="TestPassword123!",
            department=self.department,
            is_staff=True,
        )

        permission = Permission.objects.get(
            content_type__app_label="requisitions",
            codename="approve_requisition",
        )
        self.manager.user_permissions.add(permission)

        self.category = ItemCategory.objects.create(
            name="Office Supplies",
        )

        self.item = InventoryItem.objects.create(
            item_code="TEST-REJ-001",
            name="Test Paper",
            category=self.category,
            unit_of_measure=InventoryItem.Unit.REAM,
            quantity_on_hand=50,
            reorder_level=5,
        )

        self.requisition = Requisition.objects.create(
            requested_by=self.employee,
            department=self.department,
        )

        self.line = RequisitionItem.objects.create(
             requisition=self.requisition,
             inventory_item=self.item,
             quantity_requested=10,
             unit_of_measure=InventoryItem.Unit.REAM,
        )

        self.requisition.refresh_from_db()
        self.requisition.status = Requisition.Status.SUBMITTED
        self.requisition.save(
            update_fields=["status", "updated_at"]
        )

    def test_rejection_does_not_reserve_inventory(self):
        approval = decide_requisition(
            requisition=self.requisition,
            approver=self.manager,
            decision=ApprovalHistory.Decision.REJECTED,
            remarks="Request does not meet current requirements.",
        )

        self.requisition.refresh_from_db()
        self.item.refresh_from_db()

        self.assertEqual(
            self.requisition.status,
            Requisition.Status.REJECTED,
        )
        self.assertEqual(
            approval.decision,
            ApprovalHistory.Decision.REJECTED,
        )
        self.assertFalse(
            StockReservation.objects.filter(
                requisition_item=self.line,
            ).exists()
        )
        self.assertEqual(self.item.quantity_reserved, 0)
        self.assertEqual(self.item.quantity_on_hand, 50)
        self.assertEqual(self.item.quantity_available, 50)

    def test_rejection_without_remarks_is_rejected(self):
        with self.assertRaises(ValidationError):
            decide_requisition(
                requisition=self.requisition,
                approver=self.manager,
                decision=ApprovalHistory.Decision.REJECTED,
                remarks="",
            )

        self.requisition.refresh_from_db()
        self.item.refresh_from_db()

        self.assertEqual(
            self.requisition.status,
            Requisition.Status.SUBMITTED,
        )
        self.assertEqual(self.item.quantity_reserved, 0)
        self.assertFalse(
            StockReservation.objects.filter(
                requisition_item=self.line,
            ).exists()
        )

    def test_requester_cannot_reject_own_requisition(self):
        with self.assertRaises(PermissionDenied):
            decide_requisition(
                requisition=self.requisition,
                approver=self.employee,
                decision=ApprovalHistory.Decision.REJECTED,
                remarks="Testing authorization.",
            )

        self.requisition.refresh_from_db()

        self.assertEqual(
            self.requisition.status,
            Requisition.Status.SUBMITTED,
        )

    def test_approval_reserves_only_available_stock(self):
        # Reduce physical stock to 5 while the request is for 10.
        self.item.quantity_on_hand = 5
        self.item.save(
            update_fields=["quantity_on_hand", "updated_at"]
        )

        approval = decide_requisition(
            requisition=self.requisition,
            approver=self.manager,
            decision=ApprovalHistory.Decision.APPROVED,
            remarks="Approved based on available inventory.",
        )

        self.item.refresh_from_db()
        self.requisition.refresh_from_db()

        reservation = StockReservation.objects.get(
            requisition_item=self.line,
        )

        self.assertEqual(
            self.requisition.status,
            Requisition.Status.APPROVED,
        )
        self.assertEqual(
            approval.decision,
            ApprovalHistory.Decision.APPROVED,
        )
        self.assertEqual(reservation.quantity_requested, 10)
        self.assertEqual(reservation.quantity_reserved, 5)
        self.assertEqual(
            reservation.status,
            StockReservation.Status.ACTIVE,
        )
        self.assertEqual(self.item.quantity_on_hand, 5)
        self.assertEqual(self.item.quantity_reserved, 5)
        self.assertEqual(self.item.quantity_available, 0)

    def test_approval_with_zero_available_stock(self):
        self.item.quantity_on_hand = 0
        self.item.save(
            update_fields=["quantity_on_hand", "updated_at"]
        )

        decide_requisition(
            requisition=self.requisition,
            approver=self.manager,
            decision=ApprovalHistory.Decision.APPROVED,
            remarks="Approved for purchasing.",
        )

        self.item.refresh_from_db()
        self.requisition.refresh_from_db()

        reservation = StockReservation.objects.get(
            requisition_item=self.line,
        )

        self.assertEqual(
            self.requisition.status,
            Requisition.Status.APPROVED,
        )
        self.assertEqual(reservation.quantity_reserved, 0)
        self.assertEqual(self.item.quantity_reserved, 0)
        self.assertEqual(self.item.quantity_on_hand, 0)
        self.assertEqual(self.item.quantity_available, 0)

    def test_cancellation_releases_reserved_inventory(self):
        decide_requisition(
            requisition=self.requisition,
            approver=self.manager,
            decision=ApprovalHistory.Decision.APPROVED,
            remarks="Approved for testing cancellation.",
        )

        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity_reserved, 10)

        change_status(
            requisition=self.requisition,
            new_status=Requisition.Status.CANCELLED,
            user=self.employee,
            remarks="Requester cancelled the request.",
        )

        self.requisition.refresh_from_db()
        self.item.refresh_from_db()

        reservation = StockReservation.objects.get(
            requisition_item=self.line,
        )

        self.assertEqual(
            self.requisition.status,
            Requisition.Status.CANCELLED,
        )
        self.assertEqual(
            reservation.status,
            StockReservation.Status.RELEASED,
        )
        self.assertIsNotNone(reservation.released_at)
        self.assertEqual(self.item.quantity_on_hand, 50)
        self.assertEqual(self.item.quantity_reserved, 0)
        self.assertEqual(self.item.quantity_available, 50)


    def test_duplicate_reservation_does_not_reserve_twice(self):
        decide_requisition(
            requisition=self.requisition,
            approver=self.manager,
            decision=ApprovalHistory.Decision.APPROVED,
            remarks="Approved for duplicate reservation test.",
        )

        self.item.refresh_from_db()

        self.assertEqual(self.item.quantity_reserved, 10)

        reserve_for_requisition(
            self.requisition,
            self.manager,
        )

        self.item.refresh_from_db()

        self.assertEqual(
            StockReservation.objects.filter(
                requisition_item=self.line,
            ).count(),
            1,
        )
        self.assertEqual(self.item.quantity_reserved, 10)
        self.assertEqual(self.item.quantity_available, 40)

    def test_inventory_transaction_cannot_be_edited_or_deleted(self):
        decide_requisition(
            requisition=self.requisition,
            approver=self.manager,
            decision=ApprovalHistory.Decision.APPROVED,
            remarks="Approved for ledger protection test.",
        )

        transaction_record = InventoryTransaction.objects.get(
            inventory_item=self.item,
            transaction_type=InventoryTransaction.TransactionType.RESERVE,
        )

        transaction_record.remarks = "Attempted modification"

        with self.assertRaises(PermissionDenied):
            transaction_record.save()

        with self.assertRaises(PermissionDenied):
            transaction_record.delete()

        self.assertTrue(
            InventoryTransaction.objects.filter(
                pk=transaction_record.pk,
            ).exists()
        )


    def test_stock_preview_with_sufficient_inventory(self):
        check = stock_check(self.requisition)

        row = check["rows"][0]

        self.assertTrue(check["is_preview"])
        self.assertEqual(row["available"], 50)
        self.assertEqual(row["reserved"], 10)
        self.assertEqual(row["shortage"], 0)
        self.assertEqual(row["outcome"], "sufficient")
        self.assertEqual(check["overall"], "sufficient")

    def test_stock_preview_with_partial_inventory(self):
        self.item.quantity_on_hand = 5
        self.item.save(
            update_fields=["quantity_on_hand", "updated_at"]
        )

        check = stock_check(self.requisition)

        row = check["rows"][0]

        self.assertTrue(check["is_preview"])
        self.assertEqual(row["available"], 5)
        self.assertEqual(row["reserved"], 5)
        self.assertEqual(row["shortage"], 5)
        self.assertEqual(row["outcome"], "partial")
        self.assertEqual(check["overall"], "shortage")

    def test_stock_preview_with_zero_inventory(self):
        self.item.quantity_on_hand = 0
        self.item.save(
            update_fields=["quantity_on_hand", "updated_at"]
        )

        check = stock_check(self.requisition)

        row = check["rows"][0]

        self.assertTrue(check["is_preview"])
        self.assertEqual(row["available"], 0)
        self.assertEqual(row["reserved"], 0)
        self.assertEqual(row["shortage"], 10)
        self.assertEqual(row["outcome"], "none")
        self.assertEqual(check["overall"], "shortage")
