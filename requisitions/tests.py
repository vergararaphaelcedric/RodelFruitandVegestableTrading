from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from accounts.models import Department, User
from inventory.models import InventoryItem, ItemCategory

from .models import Requisition, RequisitionItem


class RequisitionTestBase(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name="Finance",
            code="FIN",
        )

        self.user = User.objects.create_user(
            "juan",
            password="pass12345",
            department=self.dept,
        )

        self.cat = ItemCategory.objects.create(
            name="Office Supplies",
        )

        self.paper = InventoryItem.objects.create(
            name="Bond Paper A4",
            item_code="OFF-0001",
            category=self.cat,
            unit_of_measure="ream",
            quantity_on_hand=Decimal("100"),
        )

        self.req = Requisition.objects.create(
            requested_by=self.user,
            department=self.dept,
            purpose="Monthly supplies",
        )


class RequisitionTests(RequisitionTestBase):

    def test_number_generated_from_id(self):
        self.assertEqual(
            self.req.requisition_number,
            f"REQ-{self.req.pk:04d}",
        )

        self.req.refresh_from_db()

        self.assertTrue(
            self.req.requisition_number.startswith("REQ-")
        )

    def test_numbers_are_unique_and_sequential(self):
        r2 = Requisition.objects.create(
            requested_by=self.user,
            department=self.dept,
            purpose="Another",
        )

        self.assertNotEqual(
            self.req.requisition_number,
            r2.requisition_number,
        )

        self.assertEqual(r2.pk, self.req.pk + 1)

    def test_number_unchanged_on_resave(self):
        number = self.req.requisition_number

        self.req.purpose = "Edited"
        self.req.save()
        self.req.refresh_from_db()

        self.assertEqual(
            self.req.requisition_number,
            number,
        )

    def test_defaults(self):
        self.assertEqual(
            self.req.status,
            Requisition.Status.DRAFT,
        )

        self.assertIsNotNone(self.req.request_date)

    def test_reverse_relations(self):
        self.assertIn(
            self.req,
            self.user.requisitions.all(),
        )

        self.assertIn(
            self.req,
            self.dept.requisitions.all(),
        )

    def test_user_with_requisitions_is_protected(self):
        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_department_with_requisitions_is_protected(self):
        with self.assertRaises(ProtectedError):
            self.dept.delete()


class RequisitionItemTests(RequisitionTestBase):

    def test_inventory_line_copies_name_and_unit(self):
        line = RequisitionItem.objects.create(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("10"),
        )

        self.assertEqual(
            line.item_description,
            "Bond Paper A4",
        )

        self.assertEqual(
            line.unit_of_measure,
            "ream",
        )

        self.assertFalse(line.is_custom_item)

    def test_custom_item_not_in_inventory(self):
        line = RequisitionItem.objects.create(
            requisition=self.req,
            item_description="Whiteboard, 4x6 ft",
            unit_of_measure="pc",
            quantity_requested=Decimal("2"),
        )

        line.full_clean()

        self.assertTrue(line.is_custom_item)
        self.assertIsNone(line.inventory_item)

    def test_multiple_lines_per_requisition(self):
        RequisitionItem.objects.create(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("5"),
        )

        RequisitionItem.objects.create(
            requisition=self.req,
            item_description="Flip chart",
            unit_of_measure="pc",
            quantity_requested=Decimal("1"),
        )

        RequisitionItem.objects.create(
            requisition=self.req,
            item_description="Marker set",
            unit_of_measure="set",
            quantity_requested=Decimal("3"),
        )

        self.assertEqual(self.req.items.count(), 3)

    def test_line_needs_item_or_description(self):
        line = RequisitionItem(
            requisition=self.req,
            unit_of_measure="pc",
            quantity_requested=Decimal("1"),
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            line.save()

    def test_custom_item_needs_unit(self):
        line = RequisitionItem(
            requisition=self.req,
            item_description="Thing",
            quantity_requested=Decimal("1"),
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_requested_quantity_must_be_positive(self):
        line = RequisitionItem(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("0"),
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            line.save()

    def test_fulfilled_cannot_exceed_requested(self):
        line = RequisitionItem(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("5"),
            quantity_fulfilled=Decimal("6"),
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            line.save()

    def test_outstanding_and_fully_fulfilled(self):
        line = RequisitionItem.objects.create(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("10"),
            quantity_fulfilled=Decimal("4"),
        )

        self.assertEqual(
            line.quantity_outstanding,
            Decimal("6"),
        )

        self.assertFalse(line.is_fully_fulfilled)

        line.quantity_fulfilled = Decimal("10")
        line.save()

        self.assertTrue(line.is_fully_fulfilled)

    def test_same_inventory_item_twice_rejected(self):
        RequisitionItem.objects.create(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("1"),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            RequisitionItem.objects.create(
                requisition=self.req,
                inventory_item=self.paper,
                quantity_requested=Decimal("2"),
            )

    def test_deleting_requisition_deletes_lines(self):
        RequisitionItem.objects.create(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("1"),
        )

        self.req.delete()

        self.assertEqual(
            RequisitionItem.objects.count(),
            0,
        )

    def test_inventory_item_with_lines_is_protected(self):
        RequisitionItem.objects.create(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("1"),
        )

        with self.assertRaises(ProtectedError):
            self.paper.delete()

    def test_inventory_reverse_relation(self):
        line = RequisitionItem.objects.create(
            requisition=self.req,
            inventory_item=self.paper,
            quantity_requested=Decimal("1"),
        )

        self.assertIn(
            line,
            self.paper.requisition_lines.all(),
        )


from django.urls import reverse


class RequisitionAccessTests(RequisitionTestBase):

    def setUp(self):
        super().setUp()

        self.user.role = User.Role.EMPLOYEE
        self.user.save()

        self.other_user = User.objects.create_user(
            "maria",
            password="pass12345",
            department=self.dept,
            role=User.Role.EMPLOYEE,
        )

        self.other_req = Requisition.objects.create(
            requested_by=self.other_user,
            department=self.dept,
            purpose="Private request",
        )

        self.client.login(
            username="juan",
            password="pass12345",
        )

    def test_employee_list_shows_only_own_requisitions(self):
        response = self.client.get(
            reverse("my-requisitions")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.req.requisition_number,
        )
        self.assertNotContains(
            response,
            self.other_req.requisition_number,
        )

    def test_employee_cannot_view_another_users_details(self):
        response = self.client.get(
            reverse(
                "requisition-detail",
                args=[self.other_req.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_employee_cannot_track_another_users_requisition(self):
        response = self.client.get(
            reverse(
                "requisition-tracking",
                args=[self.other_req.pk],
            )
        )

        self.assertEqual(response.status_code, 404)
