
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from accounts.models import Department
from requisitions.models import Requisition, RequisitionItem, StockReservation

from .models import (
    Asset,
    InventoryItem,
    InventoryTransaction,
    ItemAssignment,
    ItemCategory,
)
from .services import (
    acknowledge_item_assignment,
    issue_requisition_item,
)


User = get_user_model()


class Day17IssuanceTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            name="Test Department",
            code="TEST",
        )

        self.employee = User.objects.create_user(
            username="test_employee",
            password="test-password",
            role="employee",
            department=self.department,
        )

        self.inventory_staff = User.objects.create_user(
            username="test_inventory_staff",
            password="test-password",
            role="inventory_staff",
        )

        self.employee.user_permissions.add(
            Permission.objects.get(
                codename="acknowledge_item_assignments",
                content_type__app_label="inventory",
            )
        )

        self.inventory_staff.user_permissions.add(
            Permission.objects.get(
                codename="issue_items",
                content_type__app_label="inventory",
            )
        )

        self.category = ItemCategory.objects.create(
            name="Day 17 Test Category",
            description="Test category for issuance",
        )

    def create_item(self, **overrides):
        data = {
            "name": "Test Office Item",
            "item_code": "TEST-0001",
            "category": self.category,
            "unit_of_measure": InventoryItem.Unit.PIECE,
            "quantity_on_hand": Decimal("10"),
            "reorder_level": Decimal("2"),
        }
        data.update(overrides)
        return InventoryItem.objects.create(**data)

    def create_approved_requisition(self, item, quantity):
        requisition = Requisition.objects.create(
            requested_by=self.employee,
            department=self.department,
            purpose="Day 17 issuance test",
            status=Requisition.Status.APPROVED,
        )

        line = RequisitionItem.objects.create(
            requisition=requisition,
            inventory_item=item,
            quantity_requested=Decimal(str(quantity)),
        )

        return requisition, line

    def test_issue_consumes_reserved_stock_and_creates_ledger(self):
        item = self.create_item(
            quantity_on_hand=Decimal("10"),
            quantity_reserved=Decimal("5"),
        )

        requisition, line = self.create_approved_requisition(item, 5)

        reservation = StockReservation.objects.create(
            requisition_item=line,
            inventory_item=item,
            quantity_requested=Decimal("5"),
            quantity_reserved=Decimal("5"),
            quantity_consumed=Decimal("0"),
            status=StockReservation.Status.ACTIVE,
            reserved_by=self.inventory_staff,
        )

        result = issue_requisition_item(
            user=self.inventory_staff,
            requisition_item_id=line.pk,
            quantity=Decimal("2"),
        )

        item.refresh_from_db()
        reservation.refresh_from_db()
        line.refresh_from_db()
        requisition.refresh_from_db()

        self.assertEqual(item.quantity_on_hand, Decimal("8"))
        self.assertEqual(item.quantity_reserved, Decimal("3"))
        self.assertEqual(reservation.quantity_consumed, Decimal("2"))
        self.assertEqual(reservation.remaining_reserved, Decimal("3"))
        self.assertEqual(line.quantity_fulfilled, Decimal("2"))

        self.assertEqual(
            requisition.status,
            Requisition.Status.PARTIALLY_FULFILLED,
        )

        self.assertEqual(
            result["issued_quantity"],
            Decimal("2"),
        )

        ledger = InventoryTransaction.objects.get(
            transaction_type=InventoryTransaction.TransactionType.ISSUE,
        )

        self.assertEqual(ledger.on_hand_change, Decimal("-2"))
        self.assertEqual(ledger.reserved_change, Decimal("-2"))
        self.assertEqual(ledger.on_hand_after, Decimal("8"))
        self.assertEqual(ledger.reserved_after, Decimal("3"))

        self.assertEqual(
            ItemAssignment.objects.filter(
                requisition_item=line,
            ).count(),
            1,
        )

    def test_durable_equipment_creates_asset_and_requires_acknowledgement(self):
        item = self.create_item(
            item_code="TEST-0002",
            name="Test Durable Equipment",
            quantity_on_hand=Decimal("1"),
            quantity_reserved=Decimal("0"),
            is_durable_equipment=True,
        )

        requisition, line = self.create_approved_requisition(item, 1)

        result = issue_requisition_item(
            user=self.inventory_staff,
            requisition_item_id=line.pk,
            quantity=Decimal("1"),
            serial_numbers=["TEST-SERIAL-001"],
        )

        assignment = result["assignments"][0]

        item.refresh_from_db()
        requisition.refresh_from_db()

        self.assertEqual(item.quantity_on_hand, Decimal("0"))
        self.assertEqual(Asset.objects.count(), 1)

        asset = Asset.objects.get(
            serial_number="TEST-SERIAL-001",
        )

        self.assertEqual(asset.status, Asset.Status.ASSIGNED)
        self.assertEqual(assignment.asset, asset)
        self.assertEqual(
            assignment.status,
            ItemAssignment.Status.PENDING_ACKNOWLEDGEMENT,
        )

        self.assertEqual(
            requisition.status,
            Requisition.Status.PARTIALLY_FULFILLED,
        )

        acknowledge_item_assignment(
            user=self.employee,
            assignment_id=assignment.pk,
            acknowledgement_note="Item received.",
        )

        assignment.refresh_from_db()
        requisition.refresh_from_db()

        self.assertEqual(
            assignment.status,
            ItemAssignment.Status.ACKNOWLEDGED,
        )
        self.assertIsNotNone(assignment.acknowledged_at)
        self.assertEqual(
            requisition.status,
            Requisition.Status.FULFILLED,
        )

    def test_employee_cannot_issue_inventory(self):
        item = self.create_item()

        requisition, line = self.create_approved_requisition(item, 1)

        with self.assertRaises(PermissionDenied):
            issue_requisition_item(
                user=self.employee,
                requisition_item_id=line.pk,
                quantity=Decimal("1"),
            )

    def test_employee_cannot_acknowledge_another_employees_assignment(self):
        item = self.create_item(
            item_code="TEST-0003",
        )

        requisition, line = self.create_approved_requisition(item, 1)

        result = issue_requisition_item(
            user=self.inventory_staff,
            requisition_item_id=line.pk,
            quantity=Decimal("1"),
        )

        assignment = result["assignments"][0]

        another_employee = User.objects.create_user(
            username="another_employee",
            password="test-password",
            role="employee",
            department=self.department,
        )

        another_employee.user_permissions.add(
            Permission.objects.get(
                codename="acknowledge_item_assignments",
                content_type__app_label="inventory",
            )
        )

        with self.assertRaises(PermissionDenied):
            acknowledge_item_assignment(
                user=another_employee,
                assignment_id=assignment.pk,
                acknowledgement_note="Not my item.",
            )
