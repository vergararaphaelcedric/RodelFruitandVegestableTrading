
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import ItemCategory, InventoryItem


class InventoryModelTests(TestCase):

    def setUp(self):
        self.category = ItemCategory.objects.create(
            name="Office Supplies",
            description="General office materials",
        )

    def create_item(self, **overrides):
        data = {
            "name": "Bond Paper A4",
            "item_code": "OFF-0001",
            "category": self.category,
            "unit_of_measure": InventoryItem.Unit.REAM,
            "quantity_on_hand": Decimal("20"),
            "reorder_level": Decimal("5"),
        }
        data.update(overrides)
        return InventoryItem.objects.create(**data)

    def test_add_and_view_inventory_item(self):
        item = self.create_item()

        saved_item = InventoryItem.objects.get(pk=item.pk)

        self.assertEqual(saved_item.name, "Bond Paper A4")
        self.assertEqual(saved_item.item_code, "OFF-0001")
        self.assertEqual(saved_item.category, self.category)

    def test_edit_inventory_item(self):
        item = self.create_item()

        item.name = "Updated Bond Paper A4"
        item.quantity_on_hand = Decimal("50")
        item.save()

        updated_item = InventoryItem.objects.get(pk=item.pk)

        self.assertEqual(updated_item.name, "Updated Bond Paper A4")
        self.assertEqual(updated_item.quantity_on_hand, Decimal("50"))

    def test_item_code_is_converted_to_uppercase(self):
        item = self.create_item(item_code="off-0002")

        self.assertEqual(item.item_code, "OFF-0002")

    def test_low_stock_detection(self):
        item = self.create_item(
            quantity_on_hand=Decimal("3"),
            reorder_level=Decimal("5"),
        )

        self.assertTrue(item.is_low_stock)

        item.quantity_on_hand = Decimal("10")
        item.save()

        self.assertFalse(item.is_low_stock)

    def test_negative_stock_is_rejected(self):
        item = InventoryItem(
            name="Invalid Item",
            item_code="OFF-0003",
            category=self.category,
            unit_of_measure=InventoryItem.Unit.PIECE,
            quantity_on_hand=Decimal("-1"),
            reorder_level=Decimal("0"),
        )

        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_database_prevents_negative_stock(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryItem.objects.create(
                    name="Invalid Stock Item",
                    item_code="OFF-0004",
                    category=self.category,
                    unit_of_measure=InventoryItem.Unit.PIECE,
                    quantity_on_hand=Decimal("-1"),
                    reorder_level=Decimal("0"),
                )
