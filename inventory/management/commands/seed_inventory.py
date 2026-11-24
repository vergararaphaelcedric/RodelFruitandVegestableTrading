
from decimal import Decimal

from django.core.management.base import BaseCommand

from inventory.models import ItemCategory, InventoryItem


class Command(BaseCommand):
    help = "Add sample inventory categories and items"

    def handle(self, *args, **options):
        categories = {
            "Office Supplies": "Paper, pens, folders, and office materials.",
            "Cleaning Supplies": "Cleaning and sanitation materials.",
            "IT Equipment": "Computer equipment and IT accessories.",
            "Furniture": "Office furniture and fixtures.",
            "Medical Supplies": "First aid and basic medical supplies.",
        }

        category_map = {}

        for name, description in categories.items():
            category, created = ItemCategory.objects.get_or_create(
                name=name,
                defaults={"description": description},
            )
            category_map[name] = category

        items = [
            {
                "item_code": "OFF-0001",
                "name": "Bond Paper A4, 70gsm",
                "category": "Office Supplies",
                "description": "A4-sized bond paper for office printing.",
                "unit_of_measure": "ream",
                "quantity_on_hand": "120",
                "reorder_level": "50",
                "is_durable_equipment": False,
            },
            {
                "item_code": "OFF-0002",
                "name": "Ballpoint Pen, Black",
                "category": "Office Supplies",
                "description": "Black ink ballpoint pens.",
                "unit_of_measure": "box",
                "quantity_on_hand": "35",
                "reorder_level": "20",
                "is_durable_equipment": False,
            },
            {
                "item_code": "OFF-0003",
                "name": "Long Folder, Manila",
                "category": "Office Supplies",
                "description": "Manila folders for document filing.",
                "unit_of_measure": "pack",
                "quantity_on_hand": "18",
                "reorder_level": "25",
                "is_durable_equipment": False,
            },
            {
                "item_code": "OFF-0004",
                "name": "Stapler, Heavy Duty",
                "category": "Office Supplies",
                "description": "Heavy-duty stapler for office use.",
                "unit_of_measure": "pc",
                "quantity_on_hand": "14",
                "reorder_level": "5",
                "is_durable_equipment": True,
            },
            {
                "item_code": "CLN-0001",
                "name": "Liquid Hand Soap, 500ml",
                "category": "Cleaning Supplies",
                "description": "Liquid hand soap for office wash areas.",
                "unit_of_measure": "bottle",
                "quantity_on_hand": "60",
                "reorder_level": "30",
                "is_durable_equipment": False,
            },
            {
                "item_code": "CLN-0002",
                "name": "Disinfectant Spray, 1L",
                "category": "Cleaning Supplies",
                "description": "Surface disinfectant spray.",
                "unit_of_measure": "bottle",
                "quantity_on_hand": "8",
                "reorder_level": "15",
                "is_durable_equipment": False,
            },
            {
                "item_code": "CLN-0003",
                "name": "Trash Bags, Large",
                "category": "Cleaning Supplies",
                "description": "Large garbage bags for office waste bins.",
                "unit_of_measure": "roll",
                "quantity_on_hand": "40",
                "reorder_level": "20",
                "is_durable_equipment": False,
            },
            {
                "item_code": "CLN-0004",
                "name": "Floor Cleaner",
                "category": "Cleaning Supplies",
                "description": "Liquid floor cleaning solution.",
                "unit_of_measure": "l",
                "quantity_on_hand": "22.50",
                "reorder_level": "10",
                "is_durable_equipment": False,
            },
            {
                "item_code": "ITE-0001",
                "name": "Laptop, 14-inch, 16GB RAM",
                "category": "IT Equipment",
                "description": "Laptop for employee office work.",
                "unit_of_measure": "pc",
                "quantity_on_hand": "9",
                "reorder_level": "3",
                "is_durable_equipment": True,
            },
            {
                "item_code": "ITE-0002",
                "name": "Wireless Mouse",
                "category": "IT Equipment",
                "description": "Wireless computer mouse.",
                "unit_of_measure": "pc",
                "quantity_on_hand": "27",
                "reorder_level": "10",
                "is_durable_equipment": True,
            },
            {
                "item_code": "ITE-0003",
                "name": "Network Cable Cat6",
                "category": "IT Equipment",
                "description": "Cat6 Ethernet cable for network connections.",
                "unit_of_measure": "m",
                "quantity_on_hand": "300",
                "reorder_level": "100",
                "is_durable_equipment": False,
            },
            {
                "item_code": "ITE-0004",
                "name": "Toner Cartridge, Black",
                "category": "IT Equipment",
                "description": "Black toner cartridge for office printers.",
                "unit_of_measure": "pc",
                "quantity_on_hand": "4",
                "reorder_level": "6",
                "is_durable_equipment": False,
            },
            {
                "item_code": "FUR-0001",
                "name": "Ergonomic Office Chair",
                "category": "Furniture",
                "description": "Adjustable ergonomic chair for employees.",
                "unit_of_measure": "pc",
                "quantity_on_hand": "12",
                "reorder_level": "4",
                "is_durable_equipment": True,
            },
            {
                "item_code": "FUR-0002",
                "name": "Steel Filing Cabinet, 4-Drawer",
                "category": "Furniture",
                "description": "Four-drawer steel filing cabinet.",
                "unit_of_measure": "pc",
                "quantity_on_hand": "6",
                "reorder_level": "2",
                "is_durable_equipment": True,
            },
            {
                "item_code": "MED-0001",
                "name": "First Aid Kit",
                "category": "Medical Supplies",
                "description": "Basic first aid kit for office emergencies.",
                "unit_of_measure": "set",
                "quantity_on_hand": "10",
                "reorder_level": "5",
                "is_durable_equipment": False,
            },
            {
                "item_code": "MED-0002",
                "name": "Face Mask, Surgical",
                "category": "Medical Supplies",
                "description": "Disposable surgical face masks.",
                "unit_of_measure": "box",
                "quantity_on_hand": "0",
                "reorder_level": "10",
                "is_durable_equipment": False,
            },
        ]

        created_count = 0

        for item_data in items:
            item_data["category"] = category_map[item_data["category"]]
            item_data["quantity_on_hand"] = Decimal(
                item_data["quantity_on_hand"]
            )
            item_data["reorder_level"] = Decimal(
                item_data["reorder_level"]
            )

            item, created = InventoryItem.objects.get_or_create(
                item_code=item_data["item_code"],
                defaults=item_data,
            )

            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully ensured {len(categories)} categories."
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{created_count} new inventory items created."
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Total sample inventory items: {InventoryItem.objects.count()}"
            )
        )
