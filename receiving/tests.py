
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Department
from inventory.models import (
    InventoryItem,
    InventoryTransaction,
    InventoryRegistration,
    ItemCategory,
)
from inventory.services import register_accepted_receipt_item
from procurement.models import (
    BudgetApproval,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierQuotation,
)
from receiving.models import (
    DeliveryDiscrepancy,
    DeliveryReceiptItem,
)
from receiving.services import record_delivery
from requisitions.models import Requisition, RequisitionItem


User = get_user_model()


class ReceivingServiceTests(TestCase):

    def setUp(self):
        # -------------------------------------------------
        # USERS AND PERMISSIONS
        # -------------------------------------------------

        self.department = Department.objects.create(
            name="Test Department",
            code="TEST",
        )

        self.receiving_user = User.objects.create_user(
            username="receiving_test",
            password="test-password",
            role=User.Role.RECEIVING_STAFF,
            department=self.department,
        )

        self.manager = User.objects.create_user(
            username="manager_test",
            password="test-password",
            role=User.Role.MANAGER,
            department=self.department,
        )

        required_permissions = Permission.objects.filter(
            content_type__app_label="receiving",
            codename__in=[
                "add_deliveryreceipt",
                "add_deliveryreceiptitem",
                "add_deliverydiscrepancy",
            ],
        )

        self.receiving_user.user_permissions.add(
            *required_permissions
        )

        registration_permission = Permission.objects.get(
            content_type__app_label="inventory",
            codename="add_inventoryregistration",
        )

        self.inventory_staff = User.objects.create_user(
            username="inventory_test",
            password="test-password",
            role=User.Role.INVENTORY_STAFF,
            department=self.department,
        )

        self.inventory_staff.user_permissions.add(
            registration_permission
        )

        # -------------------------------------------------
        # INVENTORY
        # -------------------------------------------------

        self.category = ItemCategory.objects.create(
            name="Test Supplies",
            description="Category for receiving tests.",
        )

        self.inventory_item = InventoryItem.objects.create(
            name="Test Bond Paper",
            item_code="TEST-001",
            category=self.category,
            unit_of_measure=InventoryItem.Unit.REAM,
            quantity_on_hand=Decimal("0"),
            reorder_level=Decimal("5"),
            is_active=True,
        )

        # -------------------------------------------------
        # REQUISITION
        # -------------------------------------------------

        self.requisition = Requisition.objects.create(
            requested_by=self.receiving_user,
            department=self.department,
            purpose="Automated receiving module test.",
            status=Requisition.Status.APPROVED,
        )

        self.requisition_item = RequisitionItem.objects.create(
            requisition=self.requisition,
            inventory_item=self.inventory_item,
            quantity_requested=Decimal("5"),
        )

        # -------------------------------------------------
        # PURCHASE REQUEST
        # -------------------------------------------------

        self.purchase_request = PurchaseRequest.objects.create(
            requisition=self.requisition,
            status=PurchaseRequest.Status.ORDERED,
            created_by=self.receiving_user,
            notes="Receiving test purchase request.",
        )

        self.purchase_request_item = PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            requisition_item=self.requisition_item,
            inventory_item=self.inventory_item,
            item_description=self.inventory_item.name,
            unit_of_measure=self.inventory_item.unit_of_measure,
            quantity_requested=Decimal("5"),
            quantity_reserved=Decimal("0"),
            quantity_shortage=Decimal("5"),
        )

        # -------------------------------------------------
        # SUPPLIER AND QUOTATION
        # -------------------------------------------------

        self.supplier = Supplier.objects.create(
            name="Test Supplier",
            contact_person="Test Contact",
            email="supplier@example.com",
            address="Test Address",
        )

        self.quotation = SupplierQuotation.objects.create(
            supplier=self.supplier,
            purchase_request_item=self.purchase_request_item,
            quantity=Decimal("5"),
            unit_price=Decimal("100"),
            valid_until=timezone.localdate() + timedelta(days=30),
            created_by=self.receiving_user,
        )

        # -------------------------------------------------
        # APPROVED BUDGET
        # -------------------------------------------------

        self.budget_approval = BudgetApproval.objects.create(
            purchase_request=self.purchase_request,
            requested_by=self.receiving_user,
            total_amount=Decimal("500"),
            snapshot=[],
            status=BudgetApproval.Status.APPROVED,
            decided_by=self.manager,
            decided_at=timezone.now(),
        )

        # -------------------------------------------------
        # ISSUED PURCHASE ORDER
        # -------------------------------------------------

        self.purchase_order = PurchaseOrder.objects.create(
            purchase_request=self.purchase_request,
            budget_approval=self.budget_approval,
            supplier=self.supplier,
            supplier_name=self.supplier.name,
            supplier_address=self.supplier.address,
            supplier_contact=self.supplier.contact_person,
            supplier_email=self.supplier.email,
            status=PurchaseOrder.Status.ISSUED,
            total_amount=Decimal("500"),
            created_by=self.receiving_user,
            issued_by=self.manager,
            issued_at=timezone.now(),
        )

        self.po_item = PurchaseOrderItem.objects.create(
            purchase_order=self.purchase_order,
            purchase_request_item=self.purchase_request_item,
            quotation=self.quotation,
            inventory_item=self.inventory_item,
            item_description=self.inventory_item.name,
            unit_of_measure=self.inventory_item.unit_of_measure,
            quantity=Decimal("5"),
            unit_price=Decimal("100"),
            line_total=Decimal("500"),
        )

    def delivery_line(
        self,
        delivered,
        accepted,
        damaged=0,
        incorrect=0,
        damaged_description="",
        incorrect_description="",
    ):
        return {
            "purchase_order_item_id": self.po_item.pk,
            "delivered_quantity": delivered,
            "accepted_quantity": accepted,
            "damaged_quantity": damaged,
            "incorrect_quantity": incorrect,
            "damaged_description": damaged_description,
            "incorrect_description": incorrect_description,
        }

    # -----------------------------------------------------
    # TEST 1: ACCEPTED DELIVERY AND REGISTRATION
    # -----------------------------------------------------

    def test_accepted_delivery_adds_inventory_stock(self):
        receipt = record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-ACCEPTED-001",
            items=[
                self.delivery_line(
                    delivered=2,
                    accepted=2,
                )
            ],
        )

        self.inventory_item.refresh_from_db()

        receipt_item = DeliveryReceiptItem.objects.get(
            receipt=receipt
        )

        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("2.00"),
        )

        self.assertEqual(
            receipt_item.accepted_quantity,
            Decimal("2"),
        )

        self.assertEqual(
            receipt_item.registration_status,
            DeliveryReceiptItem.RegistrationStatus.REGISTERED,
        )

        self.assertEqual(
            receipt_item.registered_quantity,
            Decimal("2"),
        )

        self.assertEqual(
            InventoryTransaction.objects.filter(
                inventory_item=self.inventory_item,
                transaction_type=InventoryTransaction.TransactionType.RECEIPT,
            ).count(),
            1,
        )

        registration = InventoryRegistration.objects.get(
            receipt_item=receipt_item
        )

        self.assertEqual(
            registration.inventory_item,
            self.inventory_item,
        )

        self.assertEqual(
            registration.quantity,
            Decimal("2.00"),
        )

        self.assertEqual(
            registration.ledger_entry.reference,
            receipt.receipt_number,
        )

        self.assertEqual(
            registration.ledger_entry.related_reference,
            self.purchase_order.po_number,
        )

        # Stock must not be added twice.
        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("2.00"),
        )

    # -----------------------------------------------------
    # TEST 2: DAMAGED DELIVERY
    # -----------------------------------------------------

    def test_damaged_delivery_creates_discrepancy_without_stock(self):
        receipt = record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-DAMAGED-001",
            items=[
                self.delivery_line(
                    delivered=2,
                    accepted=1,
                    damaged=1,
                    damaged_description="One item arrived damaged.",
                )
            ],
        )

        self.inventory_item.refresh_from_db()

        discrepancy = DeliveryDiscrepancy.objects.get(
            receipt_item__receipt=receipt
        )

        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("1.00"),
        )

        self.assertEqual(
            discrepancy.discrepancy_type,
            DeliveryDiscrepancy.DiscrepancyType.DAMAGED,
        )

        self.assertEqual(
            discrepancy.quantity,
            Decimal("1"),
        )

        self.assertEqual(
            discrepancy.status,
            DeliveryDiscrepancy.Status.OPEN,
        )

        registration = InventoryRegistration.objects.get(
            receipt_item__receipt=receipt
        )

        self.assertEqual(
            registration.quantity,
            Decimal("1.00"),
        )

        # Damaged quantity must not be registered.
        self.assertNotEqual(
            registration.quantity,
            Decimal("2.00"),
        )

    # -----------------------------------------------------
    # TEST 3: INCORRECT DELIVERY
    # -----------------------------------------------------

    def test_incorrect_delivery_does_not_add_inventory_stock(self):
        receipt = record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-INCORRECT-001",
            items=[
                self.delivery_line(
                    delivered=1,
                    accepted=0,
                    incorrect=1,
                    incorrect_description="Wrong item delivered.",
                )
            ],
        )

        self.inventory_item.refresh_from_db()

        receipt_item = DeliveryReceiptItem.objects.get(
            receipt=receipt
        )

        discrepancy = DeliveryDiscrepancy.objects.get(
            receipt_item=receipt_item
        )

        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("0.00"),
        )

        self.assertEqual(
            receipt_item.registration_status,
            DeliveryReceiptItem.RegistrationStatus.NOT_APPLICABLE,
        )

        self.assertEqual(
            discrepancy.discrepancy_type,
            DeliveryDiscrepancy.DiscrepancyType.INCORRECT,
        )

        self.assertEqual(
            discrepancy.quantity,
            Decimal("1"),
        )

        self.assertEqual(
            InventoryTransaction.objects.filter(
                inventory_item=self.inventory_item
            ).count(),
            0,
        )

        self.assertEqual(
            InventoryRegistration.objects.filter(
                receipt_item__receipt=receipt
            ).count(),
            0,
        )

    # -----------------------------------------------------
    # TEST 4: ACCEPTED ITEM WITHOUT INVENTORY RECORD
    # -----------------------------------------------------

    def test_accepted_item_without_inventory_waits_for_setup(self):
        self.po_item.inventory_item = None
        self.po_item.save(update_fields=["inventory_item"])

        receipt = record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-SETUP-001",
            items=[
                self.delivery_line(
                    delivered=2,
                    accepted=2,
                )
            ],
        )

        receipt_item = DeliveryReceiptItem.objects.get(
            receipt=receipt
        )

        self.assertIsNone(receipt_item.inventory_item)

        self.assertEqual(
            receipt_item.registration_status,
            DeliveryReceiptItem.RegistrationStatus.AWAITING_ITEM_SETUP,
        )

        self.assertEqual(
            receipt_item.registered_quantity,
            Decimal("0"),
        )

        self.assertEqual(
            InventoryTransaction.objects.count(),
            0,
        )

        self.assertEqual(
            InventoryRegistration.objects.filter(
                receipt_item__receipt=receipt
            ).count(),
            0,
        )

    # -----------------------------------------------------
    # TEST 5: UNAUTHORIZED USER
    # -----------------------------------------------------

    def test_user_without_receiving_permissions_is_rejected(self):
        unauthorized_user = User.objects.create_user(
            username="unauthorized_test",
            password="test-password",
            role=User.Role.EMPLOYEE,
            department=self.department,
        )

        with self.assertRaises(PermissionDenied):
            record_delivery(
                user=unauthorized_user,
                purchase_order_id=self.purchase_order.pk,
                items=[
                    self.delivery_line(
                        delivered=1,
                        accepted=1,
                    )
                ],
            )

        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("0.00"),
        )

        self.assertEqual(
            self.purchase_order.delivery_receipts.count(),
            0,
        )

    # -----------------------------------------------------
    # TEST 6: INVALID QUANTITY BALANCE
    # -----------------------------------------------------

    def test_unbalanced_delivery_quantities_are_rejected(self):
        with self.assertRaises(ValidationError):
            record_delivery(
                user=self.receiving_user,
                purchase_order_id=self.purchase_order.pk,
                items=[
                    self.delivery_line(
                        delivered=3,
                        accepted=1,
                        damaged=1,
                        incorrect=0,
                    )
                ],
            )

        self.assertEqual(
            self.purchase_order.delivery_receipts.count(),
            0,
        )

        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("0.00"),
        )

    # -----------------------------------------------------
    # TEST 7: PURCHASE REQUEST COMPLETION
    # -----------------------------------------------------

    def test_purchase_request_completes_only_after_all_quantity_accepted(self):
        # First delivery: only 3 of 5 accepted.
        record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-PARTIAL-001",
            items=[
                self.delivery_line(
                    delivered=3,
                    accepted=3,
                )
            ],
        )

        self.purchase_request.refresh_from_db()

        self.assertEqual(
            self.purchase_request.status,
            PurchaseRequest.Status.ORDERED,
        )

        # Second delivery: remaining 2 accepted.
        record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-FINAL-001",
            items=[
                self.delivery_line(
                    delivered=2,
                    accepted=2,
                )
            ],
        )

        self.purchase_request.refresh_from_db()

        self.assertEqual(
            self.purchase_request.status,
            PurchaseRequest.Status.RECEIVED,
        )

        self.inventory_item.refresh_from_db()

        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("5.00"),
        )

        self.assertEqual(
            InventoryRegistration.objects.count(),
            2,
        )

        self.assertEqual(
            InventoryRegistration.objects.filter(
                inventory_item=self.inventory_item
            ).count(),
            2,
        )

    # -----------------------------------------------------
    # TEST 8: MANUAL REGISTRATION USING EXISTING ITEM
    # -----------------------------------------------------

    def test_manual_registration_adds_accepted_quantity_once(self):
        self.po_item.inventory_item = None
        self.po_item.save(update_fields=["inventory_item"])

        receipt = record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-MANUAL-001",
            items=[
                self.delivery_line(
                    delivered=2,
                    accepted=2,
                )
            ],
        )

        receipt_item = DeliveryReceiptItem.objects.get(
            receipt=receipt
        )

        registration = register_accepted_receipt_item(
            user=self.inventory_staff,
            receipt_item_id=receipt_item.pk,
            inventory_item_id=self.inventory_item.pk,
        )

        self.inventory_item.refresh_from_db()
        receipt_item.refresh_from_db()

        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("2.00"),
        )

        self.assertEqual(
            registration.quantity,
            Decimal("2.00"),
        )

        self.assertFalse(registration.item_created)

        self.assertEqual(
            receipt_item.inventory_item,
            self.inventory_item,
        )

        self.assertEqual(
            receipt_item.registration_status,
            DeliveryReceiptItem.RegistrationStatus.REGISTERED,
        )

        self.assertEqual(
            receipt_item.registered_quantity,
            Decimal("2.00"),
        )

        self.assertEqual(
            InventoryTransaction.objects.filter(
                inventory_item=self.inventory_item,
                transaction_type=InventoryTransaction.TransactionType.RECEIPT,
            ).count(),
            1,
        )

    # -----------------------------------------------------
    # TEST 9: MANUAL REGISTRATION CREATES NEW ITEM
    # -----------------------------------------------------

    def test_manual_registration_can_create_new_inventory_item(self):
        self.po_item.inventory_item = None
        self.po_item.save(update_fields=["inventory_item"])

        receipt = record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-NEW-ITEM-001",
            items=[
                self.delivery_line(
                    delivered=3,
                    accepted=3,
                )
            ],
        )

        receipt_item = DeliveryReceiptItem.objects.get(
            receipt=receipt
        )

        registration = register_accepted_receipt_item(
            user=self.inventory_staff,
            receipt_item_id=receipt_item.pk,
            new_item_data={
                "name": "Newly Registered Test Paper",
                "item_code": "NEW-TEST-001",
                "category": self.category,
                "unit_of_measure": InventoryItem.Unit.REAM,
                "description": "Created during manual registration test.",
                "reorder_level": Decimal("5"),
                "is_durable_equipment": False,
                "is_active": True,
            },
        )

        new_item = registration.inventory_item
        new_item.refresh_from_db()

        self.assertTrue(registration.item_created)

        self.assertEqual(
            new_item.quantity_on_hand,
            Decimal("3.00"),
        )

        self.assertEqual(
            registration.quantity,
            Decimal("3.00"),
        )

        self.assertEqual(
            registration.ledger_entry.reference,
            receipt.receipt_number,
        )

        self.assertEqual(
            registration.ledger_entry.related_reference,
            self.purchase_order.po_number,
        )

    # -----------------------------------------------------
    # TEST 10: PREVENT DUPLICATE REGISTRATION
    # -----------------------------------------------------

    def test_manual_registration_cannot_register_same_receipt_twice(self):
        self.po_item.inventory_item = None
        self.po_item.save(update_fields=["inventory_item"])

        receipt = record_delivery(
            user=self.receiving_user,
            purchase_order_id=self.purchase_order.pk,
            delivery_note_number="TEST-DUPLICATE-001",
            items=[
                self.delivery_line(
                    delivered=2,
                    accepted=2,
                )
            ],
        )

        receipt_item = DeliveryReceiptItem.objects.get(
            receipt=receipt
        )

        register_accepted_receipt_item(
            user=self.inventory_staff,
            receipt_item_id=receipt_item.pk,
            inventory_item_id=self.inventory_item.pk,
        )

        with self.assertRaises(ValidationError):
            register_accepted_receipt_item(
                user=self.inventory_staff,
                receipt_item_id=receipt_item.pk,
                inventory_item_id=self.inventory_item.pk,
            )

        self.inventory_item.refresh_from_db()

        self.assertEqual(
            self.inventory_item.quantity_on_hand,
            Decimal("2.00"),
        )

        self.assertEqual(
            InventoryRegistration.objects.filter(
                receipt_item=receipt_item
            ).count(),
            1,
        )
