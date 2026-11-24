
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.lookups import Exact
from django.utils import timezone


class ImmutableModel(models.Model):
    """
    Prevents recorded receiving documents from being edited or deleted.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied(
                "Recorded receiving documents cannot be modified."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(
            "Recorded receiving documents cannot be deleted."
        )


class DeliveryReceipt(ImmutableModel):

    class Outcome(models.TextChoices):
        FULLY_ACCEPTED = "fully_accepted", "Fully Accepted"
        PARTLY_ACCEPTED = "partly_accepted", "Partly Accepted"
        REJECTED = "rejected", "Rejected"

    receipt_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
    )

    purchase_order = models.ForeignKey(
        "procurement.PurchaseOrder",
        on_delete=models.PROTECT,
        related_name="delivery_receipts",
    )

    delivery_note_number = models.CharField(
        max_length=100,
        blank=True,
    )

    received_at = models.DateTimeField(
        default=timezone.now,
    )

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delivery_receipts_received",
    )

    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
    )

    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-pk"]

        indexes = [
            models.Index(fields=["purchase_order", "received_at"]),
            models.Index(fields=["outcome", "received_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied(
                "Delivery receipts cannot be modified."
            )

        if not self.receipt_number:
            super().save(*args, **kwargs)

            generated_number = f"DR-{self.pk:04d}"

            type(self).objects.filter(pk=self.pk).update(
                receipt_number=generated_number
            )

            self.receipt_number = generated_number
            return

        super().save(*args, **kwargs)

    def __str__(self):
        return self.receipt_number or "New Delivery Receipt"


class DeliveryReceiptItem(ImmutableModel):

    class RegistrationStatus(models.TextChoices):
        REGISTERED = "registered", "Registered"
        AWAITING_ITEM_SETUP = (
            "awaiting_item_setup",
            "Awaiting Item Setup",
        )
        NOT_APPLICABLE = "not_applicable", "Not Applicable"

    receipt = models.ForeignKey(
        DeliveryReceipt,
        on_delete=models.CASCADE,
        related_name="items",
    )

    purchase_order_item = models.ForeignKey(
        "procurement.PurchaseOrderItem",
        on_delete=models.PROTECT,
        related_name="delivery_receipt_items",
    )

    inventory_item = models.ForeignKey(
        "inventory.InventoryItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="delivery_receipt_items",
    )

    delivered_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    accepted_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    damaged_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    incorrect_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    registration_status = models.CharField(
        max_length=30,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.NOT_APPLICABLE,
    )

    registered_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pk"]

        constraints = [
            models.UniqueConstraint(
                fields=["receipt", "purchase_order_item"],
                name="unique_receipt_po_item",
            ),
            models.CheckConstraint(
                condition=Q(delivered_quantity__gt=0),
                name="receipt_item_delivered_gt_zero",
            ),
            models.CheckConstraint(
                condition=Q(accepted_quantity__gte=0)
                & Q(damaged_quantity__gte=0)
                & Q(incorrect_quantity__gte=0),
                name="receipt_item_quantities_nonnegative",
            ),
            models.CheckConstraint(
                condition=Exact(
                 F("accepted_quantity")
               + F("damaged_quantity")
               + F("incorrect_quantity"),
                F("delivered_quantity"),
          ),
    name="receipt_item_quantity_balance",
),
            models.CheckConstraint(
                condition=(
                    Q(registered_quantity=0)
                    | Q(registered_quantity=F("accepted_quantity"))
                ),
                name="receipt_item_registered_matches_accepted",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        registration_status="registered",
                        inventory_item__isnull=False,
                        accepted_quantity__gt=0,
                        registered_quantity=F("accepted_quantity"),
                    )
                    | Q(
                        registration_status="awaiting_item_setup",
                        inventory_item__isnull=True,
                        accepted_quantity__gt=0,
                        registered_quantity=0,
                    )
                    | Q(
                        registration_status="not_applicable",
                        registered_quantity=0,
                        accepted_quantity=0,
                    )
                ),
                name="receipt_item_registration_state_valid",
            ),
        ]

    def clean(self):
        super().clean()

        if self.purchase_order_item_id and self.receipt_id:
            if (
                self.purchase_order_item.purchase_order_id
                != self.receipt.purchase_order_id
            ):
                raise ValidationError(
                    "The purchase order item must belong to the "
                    "receipt's purchase order."
                )

    def __str__(self):
        return (
            f"{self.receipt.receipt_number} - "
            f"{self.purchase_order_item.item_description}"
        )


class DeliveryDiscrepancy(models.Model):

    class DiscrepancyType(models.TextChoices):
        DAMAGED = "damaged", "Damaged Item"
        INCORRECT = "incorrect", "Incorrect Item"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SUPPLIER_NOTIFIED = (
            "supplier_notified",
            "Supplier Notified",
        )
        REPLACEMENT_PROMISED = (
            "replacement_promised",
            "Replacement Promised",
        )
        REPLACED = "replaced", "Replaced"
        CREDITED = "credited", "Credited"
        CLOSED = "closed", "Closed"

    receipt_item = models.ForeignKey(
        DeliveryReceiptItem,
        on_delete=models.PROTECT,
        related_name="discrepancies",
    )

    discrepancy_type = models.CharField(
        max_length=20,
        choices=DiscrepancyType.choices,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.OPEN,
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    description = models.TextField()

    supplier_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    supplier_notified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    promised_replacement_date = models.DateField(
        null=True,
        blank=True,
    )

    resolution_notes = models.TextField(blank=True)

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delivery_discrepancies_reported",
    )

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="delivery_discrepancies_resolved",
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

        constraints = [
            models.UniqueConstraint(
                fields=["receipt_item", "discrepancy_type"],
                name="unique_receipt_item_discrepancy_type",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="delivery_discrepancy_quantity_gt_zero",
            ),
        ]

        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["discrepancy_type", "status"]),
        ]

    def clean(self):
        super().clean()

        if self.receipt_item_id:
            if self.discrepancy_type == self.DiscrepancyType.DAMAGED:
                maximum = self.receipt_item.damaged_quantity
            else:
                maximum = self.receipt_item.incorrect_quantity

            if self.quantity > maximum:
                raise ValidationError({
                    "quantity": (
                        "Discrepancy quantity cannot exceed the "
                        "recorded quantity for this discrepancy type."
                    )
                })

        if self.status == self.Status.REPLACEMENT_PROMISED:
            if not self.promised_replacement_date:
                raise ValidationError({
                    "promised_replacement_date": (
                        "A promised replacement date is required."
                    )
                })

        if self.status in {
            self.Status.REPLACED,
            self.Status.CREDITED,
            self.Status.CLOSED,
        }:
            if not self.resolution_notes.strip():
                raise ValidationError({
                    "resolution_notes": (
                        "Resolution notes are required to close "
                        "or resolve a discrepancy."
                    )
                })

    def __str__(self):
        return (
            f"{self.get_discrepancy_type_display()} - "
            f"{self.receipt_item.receipt.receipt_number}"
        )
