
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


class ItemCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "item categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class InventoryItem(models.Model):

    class Unit(models.TextChoices):
        PIECE = "pc", "Piece"
        BOX = "box", "Box"
        REAM = "ream", "Ream"
        PACK = "pack", "Pack"
        SET = "set", "Set"
        BOTTLE = "bottle", "Bottle"
        ROLL = "roll", "Roll"
        KILOGRAM = "kg", "Kilogram"
        LITER = "l", "Liter"
        METER = "m", "Meter"

    name = models.CharField(max_length=200)

    item_code = models.CharField(
        max_length=30,
        unique=True,
        help_text="Unique item code, e.g. OFF-0001",
    )

    category = models.ForeignKey(
        ItemCategory,
        on_delete=models.PROTECT,
        related_name="items",
    )

    description = models.TextField(blank=True)

    unit_of_measure = models.CharField(
        max_length=10,
        choices=Unit.choices,
        default=Unit.PIECE,
    )

    quantity_on_hand = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    quantity_reserved = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        editable=False,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Held for approved requisitions. Managed by the system.",
    )

    is_durable_equipment = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["category", "is_active"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_on_hand__gte=0),
                name="inventoryitem_quantity_on_hand_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(reorder_level__gte=0),
                name="inventoryitem_reorder_level_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(quantity_reserved__gte=0),
                name="inventoryitem_quantity_reserved_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(quantity_reserved__lte=F("quantity_on_hand")),
                name="inventoryitem_reserved_lte_on_hand",
            ),
        ]

    def save(self, *args, **kwargs):
        self.item_code = self.item_code.strip().upper()

        if self.pk and kwargs.get("update_fields") is None:
            kwargs["update_fields"] = [
                field.name
                for field in self._meta.concrete_fields
                if not field.primary_key
                and field.name not in {"quantity_reserved", "created_at"}
            ]

        super().save(*args, **kwargs)

    def clean(self):
        super().clean()

        if self.quantity_on_hand < self.quantity_reserved:
            raise ValidationError({
                "quantity_on_hand": (
                    "Physical stock cannot be lower than reserved stock."
                )
            })

    @property
    def quantity_available(self):
        return self.quantity_on_hand - self.quantity_reserved

    @property
    def is_low_stock(self):
        return self.quantity_available <= self.reorder_level

    def __str__(self):
        return f"{self.item_code} - {self.name}"


class InventoryTransaction(models.Model):

    class TransactionType(models.TextChoices):
        RESERVE = "reserve", "Reservation"
        RELEASE = "release", "Reservation Release"
        ADJUSTMENT = "adjustment", "Stock Adjustment"
        RECEIPT = "receipt", "Delivery Receipt"
        ISSUE = "issue", "Item Issuance"

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="transactions",
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
    )

    on_hand_change = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    reserved_change = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    on_hand_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    reserved_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    reference = models.CharField(max_length=100, blank=True)

    related_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Related purchase order number.",
    )

    remarks = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_transactions",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

        indexes = [
            models.Index(fields=["inventory_item", "created_at"]),
            models.Index(fields=["transaction_type", "created_at"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=~(
                    Q(on_hand_change=0) & Q(reserved_change=0)
                ),
                name="inventorytransaction_nonzero_change",
            ),
        ]

    @classmethod
    def record(
        cls,
        inventory_item,
        transaction_type,
        on_hand_change=Decimal("0"),
        reserved_change=Decimal("0"),
        reference="",
        remarks="",
        created_by=None,
        related_reference="",
    ):
        return cls.objects.create(
            inventory_item=inventory_item,
            transaction_type=transaction_type,
            on_hand_change=on_hand_change,
            reserved_change=reserved_change,
            on_hand_after=inventory_item.quantity_on_hand,
            reserved_after=inventory_item.quantity_reserved,
            reference=reference,
            related_reference=related_reference,
            remarks=remarks,
            created_by=created_by,
        )

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied(
                "Inventory transaction records cannot be modified."
            )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(
            "Inventory transaction records cannot be deleted."
        )

    def __str__(self):
        return (
            f"{self.inventory_item.item_code} - "
            f"{self.get_transaction_type_display()} - "
            f"{self.created_at}"
        )


class InventoryRegistration(models.Model):

    receipt_item = models.OneToOneField(
        "receiving.DeliveryReceiptItem",
        on_delete=models.PROTECT,
        related_name="inventory_registration",
    )

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="registrations",
    )

    ledger_entry = models.OneToOneField(
        InventoryTransaction,
        on_delete=models.PROTECT,
        related_name="registration",
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    item_created = models.BooleanField(default=False)

    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventory_registrations",
    )

    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-registered_at", "-pk"]

        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="inventoryregistration_quantity_gt_0",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied(
                "Inventory registration records cannot be modified."
            )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(
            "Inventory registration records cannot be deleted."
        )

    def __str__(self):
        return (
            f"{self.receipt_item.receipt.receipt_number} - "
            f"{self.inventory_item.name} - {self.quantity}"
        )

class Asset(models.Model):

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        ASSIGNED = "assigned", "Assigned"
        RETIRED = "retired", "Retired"

    asset_tag = models.CharField(
        max_length=50,
        unique=True,
    )

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="assets",
    )

    serial_number = models.CharField(
        max_length=100,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_tag"]

        constraints = [
            models.UniqueConstraint(
                fields=["serial_number"],
                condition=~Q(serial_number=""),
                name="asset_serial_number_unique",
            ),
        ]

        permissions = [
            ("manage_assets", "Can manage inventory assets"),
        ]

    def __str__(self):
        return f"{self.asset_tag} - {self.inventory_item.name}"


class ItemAssignment(models.Model):

    class Status(models.TextChoices):
        PENDING_ACKNOWLEDGEMENT = (
            "pending_acknowledgement",
            "Pending Acknowledgement",
        )
        ACKNOWLEDGED = "acknowledged", "Acknowledged"

    requisition_item = models.ForeignKey(
        "requisitions.RequisitionItem",
        on_delete=models.PROTECT,
        related_name="assignments",
    )

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="assignments",
    )

    asset = models.OneToOneField(
        Asset,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignment",
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_item_assignments",
    )

    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_item_assignments",
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_ACKNOWLEDGEMENT,
    )

    issued_at = models.DateTimeField(auto_now_add=True)

    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    acknowledgement_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-issued_at", "-pk"]

        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="itemassignment_quantity_gt_0",
            ),
            models.CheckConstraint(
                condition=(
                    Q(asset__isnull=True)
                    | Q(quantity=Decimal("1.00"))
                ),
                name="asset_assignment_quantity_one",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="pending_acknowledgement",
                        acknowledged_at__isnull=True,
                    )
                    | Q(
                        status="acknowledged",
                        acknowledged_at__isnull=False,
                    )
                ),
                name="itemassignment_acknowledgement_valid",
            ),
        ]

        permissions = [
            ("issue_items", "Can issue inventory items"),
            (
                "acknowledge_item_assignments",
                "Can acknowledge received item assignments",
            ),
        ]

    def clean(self):
        super().clean()

        if self.asset_id:
            if self.asset.inventory_item_id != self.inventory_item_id:
                raise ValidationError({
                    "asset": "The asset must belong to the selected inventory item."
                })

            if not self.inventory_item.is_durable_equipment:
                raise ValidationError({
                    "asset": "Only durable equipment can have an asset record."
                })

            if self.quantity != Decimal("1.00"):
                raise ValidationError({
                    "quantity": "An individual asset assignment must have a quantity of 1."
                })

        elif self.inventory_item.is_durable_equipment:
            raise ValidationError({
                "asset": "Durable equipment must have an individual asset record."
            })

        if self.requisition_item_id:
            if (
                self.requisition_item.inventory_item_id
                and self.requisition_item.inventory_item_id
                != self.inventory_item_id
            ):
                raise ValidationError({
                    "inventory_item": (
                        "The inventory item does not match the requisition item."
                    )
                })

            if (
                self.requisition_item.requisition.requested_by_id
                != self.assigned_to_id
            ):
                raise ValidationError({
                    "assigned_to": (
                        "Items must be assigned to the employee who submitted the requisition."
                    )
                })

    def save(self, *args, **kwargs):
        if self.pk:
            original = ItemAssignment.objects.get(pk=self.pk)

            immutable_fields = [
                "requisition_item_id",
                "inventory_item_id",
                "asset_id",
                "assigned_to_id",
                "issued_by_id",
                "quantity",
                "issued_at",
            ]

            for field in immutable_fields:
                if getattr(original, field) != getattr(self, field):
                    raise PermissionDenied(
                        "Issued assignment details cannot be modified."
                    )

            valid_acknowledgement = (
                original.status == self.Status.PENDING_ACKNOWLEDGEMENT
                and self.status == self.Status.ACKNOWLEDGED
                and self.acknowledged_at is not None
            )

            if not valid_acknowledgement and (
                original.status != self.status
                or original.acknowledged_at != self.acknowledged_at
                or original.acknowledgement_note != self.acknowledgement_note
            ):
                raise PermissionDenied(
                    "An item assignment can only be updated for acknowledgement."
                )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(
            "Item assignment records cannot be deleted."
        )

    def __str__(self):
        return (
            f"{self.inventory_item.name} - "
            f"{self.assigned_to} - {self.quantity}"
        )