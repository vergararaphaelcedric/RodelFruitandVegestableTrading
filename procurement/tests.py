
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import Department, User
from inventory.models import InventoryItem, ItemCategory
from requisitions.models import Requisition, RequisitionItem
from requisitions.stock import reserve_for_requisition

from .models import (
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierQuotation,
)
from .services import create_purchase_request, cancel_for_requisition


class PurchaseRequestTestBase(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            name="Finance",
            code="FIN",
        )

        self.employee = User.objects.create_user(
            "juan",
            password="pass12345",
            department=self.department,
        )

        self.category = ItemCategory.objects.create(
            name="Office Supplies",
        )

        self.paper = InventoryItem.objects.create(
            name="Bond Paper A4",
            item_code="OFF-0001",
            category=self.category,
            unit_of_measure="ream",
            quantity_on_hand=Decimal("100"),
        )

        self.requisition = Requisition.objects.create(
            requested_by=self.employee,
            department=self.department,
            purpose="Purchase request testing",
            status=Requisition.Status.APPROVED,
        )

    def create_inventory_line(self, quantity):
        return RequisitionItem.objects.create(
            requisition=self.requisition,
            inventory_item=self.paper,
            quantity_requested=Decimal(quantity),
        )

    def create_custom_line(self, description, unit, quantity):
        return RequisitionItem.objects.create(
            requisition=self.requisition,
            item_description=description,
            unit_of_measure=unit,
            quantity_requested=Decimal(quantity),
        )

    def reserve_stock(self):
        return reserve_for_requisition(
            self.requisition,
            self.employee,
        )

    def test_no_purchase_request_when_stock_is_sufficient(self):
        self.create_inventory_line("10")
        self.reserve_stock()

        result = create_purchase_request(
            self.requisition,
            self.employee,
        )

        self.assertIsNone(result)
        self.assertEqual(PurchaseRequest.objects.count(), 0)

    def test_purchase_request_created_for_stock_shortage(self):
        self.paper.quantity_on_hand = Decimal("3")
        self.paper.save(update_fields=["quantity_on_hand", "updated_at"])

        self.create_inventory_line("10")
        self.reserve_stock()

        purchase_request = create_purchase_request(
            self.requisition,
            self.employee,
        )

        self.assertIsNotNone(purchase_request)
        self.assertEqual(
            purchase_request.status,
            PurchaseRequest.Status.PENDING,
        )
        self.assertTrue(
            purchase_request.request_number.startswith("PR-")
        )

        item = purchase_request.items.get()

        self.assertEqual(item.quantity_requested, Decimal("10"))
        self.assertEqual(item.quantity_reserved, Decimal("3"))
        self.assertEqual(item.quantity_shortage, Decimal("7"))

    def test_custom_item_creates_purchase_request(self):
        self.create_custom_line(
            "Whiteboard",
            "pc",
            "2",
        )

        purchase_request = create_purchase_request(
            self.requisition,
            self.employee,
        )

        self.assertIsNotNone(purchase_request)

        item = purchase_request.items.get()

        self.assertEqual(item.item_description, "Whiteboard")
        self.assertIsNone(item.inventory_item)
        self.assertEqual(item.quantity_shortage, Decimal("2"))

    def test_duplicate_purchase_request_is_prevented(self):
        self.paper.quantity_on_hand = Decimal("0")
        self.paper.save(update_fields=["quantity_on_hand", "updated_at"])

        self.create_inventory_line("10")
        self.reserve_stock()

        first = create_purchase_request(
            self.requisition,
            self.employee,
        )

        second = create_purchase_request(
            self.requisition,
            self.employee,
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(PurchaseRequest.objects.count(), 1)

    def test_pending_purchase_request_is_cancelled_with_requisition(self):
        self.paper.quantity_on_hand = Decimal("0")
        self.paper.save(update_fields=["quantity_on_hand", "updated_at"])

        self.create_inventory_line("10")
        self.reserve_stock()

        purchase_request = create_purchase_request(
            self.requisition,
            self.employee,
        )

        self.assertIsNotNone(purchase_request)

        cancel_for_requisition(
            self.requisition,
            reason="Requisition cancelled",
        )

        purchase_request.refresh_from_db()

        self.assertEqual(
            purchase_request.status,
            PurchaseRequest.Status.CANCELLED,
        )
        self.assertEqual(
            purchase_request.notes,
            "Requisition cancelled",
        )

    def test_ordered_purchase_request_is_not_cancelled(self):
        self.paper.quantity_on_hand = Decimal("0")
        self.paper.save(update_fields=["quantity_on_hand", "updated_at"])

        self.create_inventory_line("10")
        self.reserve_stock()

        purchase_request = create_purchase_request(
            self.requisition,
            self.employee,
        )

        self.assertIsNotNone(purchase_request)

        purchase_request.status = PurchaseRequest.Status.ORDERED
        purchase_request.save(update_fields=["status", "updated_at"])

        cancel_for_requisition(
            self.requisition,
            reason="Requisition cancelled",
        )

        purchase_request.refresh_from_db()

        self.assertEqual(
            purchase_request.status,
            PurchaseRequest.Status.ORDERED,
        )


class SupplierTest(TestCase):
    def test_supplier_code_is_generated(self):
        supplier = Supplier.objects.create(
            name="Cebu Office Supplies",
        )

        self.assertTrue(supplier.supplier_code.startswith("SUP-"))
        self.assertEqual(len(supplier.supplier_code), 8)

    def test_supplier_name_is_normalized(self):
        supplier = Supplier.objects.create(
            name="  Cebu   Office   Supplies  ",
        )

        self.assertEqual(
            supplier.name,
            "Cebu Office Supplies",
        )

    def test_supplier_names_are_case_insensitive_unique(self):
        Supplier.objects.create(name="Cebu Office Supplies")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Supplier.objects.create(name="CEBU OFFICE SUPPLIES")

    def test_supplier_can_be_deactivated(self):
        supplier = Supplier.objects.create(
            name="Inactive Supplier",
            is_active=False,
        )

        self.assertFalse(supplier.is_active)


class SupplierQuotationTest(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            name="Finance",
            code="FIN",
        )

        self.employee = User.objects.create_user(
            "quotation_tester",
            password="pass12345",
            department=self.department,
        )

        self.category = ItemCategory.objects.create(
            name="Office Supplies",
        )

        self.paper = InventoryItem.objects.create(
            name="Bond Paper A4",
            item_code="QUOT-0001",
            category=self.category,
            unit_of_measure="ream",
            quantity_on_hand=Decimal("0"),
        )

        self.requisition = Requisition.objects.create(
            requested_by=self.employee,
            department=self.department,
            purpose="Quotation testing",
            status=Requisition.Status.APPROVED,
        )

        requisition_item = RequisitionItem.objects.create(
            requisition=self.requisition,
            inventory_item=self.paper,
            quantity_requested=Decimal("10"),
        )

        self.purchase_request = PurchaseRequest.objects.create(
            requisition=self.requisition,
            created_by=self.employee,
        )

        self.purchase_request_item = PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            requisition_item=requisition_item,
            inventory_item=self.paper,
            item_description="Bond Paper A4",
            unit_of_measure="ream",
            quantity_requested=Decimal("10"),
            quantity_reserved=Decimal("0"),
            quantity_shortage=Decimal("10"),
        )

        self.supplier = Supplier.objects.create(
            name="Cebu Office Supplies",
        )

    def create_quotation(self, **overrides):
        data = {
            "supplier": self.supplier,
            "purchase_request_item": self.purchase_request_item,
            "quantity": Decimal("5.00"),
            "unit_price": Decimal("2500.00"),
            "quotation_date": timezone.localdate(),
            "valid_until": timezone.localdate() + timedelta(days=10),
            "created_by": self.employee,
        }

        data.update(overrides)

        return SupplierQuotation.objects.create(**data)

    def test_quotation_number_is_generated(self):
        quotation = self.create_quotation()

        self.assertTrue(
            quotation.quotation_number.startswith("QT-")
        )

    def test_total_price_is_calculated_automatically(self):
        quotation = self.create_quotation()

        self.assertEqual(
            quotation.total_price,
            Decimal("12500.00"),
        )

    def test_total_price_updates_when_quantity_or_price_changes(self):
        quotation = self.create_quotation()

        quotation.quantity = Decimal("4.00")
        quotation.unit_price = Decimal("3000.00")
        quotation.save()

        quotation.refresh_from_db()

        self.assertEqual(
            quotation.total_price,
            Decimal("12000.00"),
        )

    def test_quotation_validity_date_cannot_precede_quotation_date(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_quotation(
                    quotation_date=timezone.localdate(),
                    valid_until=timezone.localdate() - timedelta(days=1),
                )

    def test_quotation_cannot_be_deleted_with_protected_supplier(self):
        self.create_quotation()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.supplier.delete()

    def test_quotation_purchase_request_property(self):
        quotation = self.create_quotation()

        self.assertEqual(
            quotation.purchase_request,
            self.purchase_request,
        )

    def test_quotation_is_not_expired_when_valid_until_is_today(self):
        quotation = self.create_quotation(
            valid_until=timezone.localdate(),
        )

        self.assertFalse(quotation.is_expired)

    def test_quotation_is_expired_when_valid_until_is_in_the_past(self):
        quotation = self.create_quotation(
            quotation_date=timezone.localdate() - timedelta(days=5),
            valid_until=timezone.localdate() - timedelta(days=1),
        )

        self.assertTrue(quotation.is_expired)
