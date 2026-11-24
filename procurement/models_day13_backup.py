
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone


# =========================================================
# PURCHASE REQUEST
# =========================================================

class PurchaseRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ORDERED = "ordered", "Ordered"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    request_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        blank=True,
    )

    requisition = models.ForeignKey(
        "requisitions.Requisition",
        on_delete=models.PROTECT,
        related_name="purchase_requests",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_purchase_requests",
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="pr_status_created_idx",
            ),
            models.Index(
                fields=["requisition"],
                name="pr_requisition_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.request_number:
            self.request_number = f"TMP-{uuid.uuid4().hex[:16]}"
            super().save(*args, **kwargs)

            self.request_number = f"PR-{self.pk:04d}"

            type(self).objects.filter(pk=self.pk).update(
                request_number=self.request_number
            )
            return

        super().save(*args, **kwargs)

    def __str__(self):
        return self.request_number or f"Purchase Request #{self.pk}"


# =========================================================
# PURCHASE REQUEST ITEM
# =========================================================

class PurchaseRequestItem(models.Model):
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )

    requisition_item = models.OneToOneField(
        "requisitions.RequisitionItem",
        on_delete=models.PROTECT,
        related_name="purchase_item",
    )

    inventory_item = models.ForeignKey(
        "inventory.InventoryItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_request_items",
    )

    item_description = models.CharField(max_length=255)

    unit_of_measure = models.CharField(
        max_length=10,
        choices=[
            ("pc", "Piece"),
            ("box", "Box"),
            ("ream", "Ream"),
            ("pack", "Pack"),
            ("set", "Set"),
            ("bottle", "Bottle"),
            ("roll", "Roll"),
            ("kg", "Kilogram"),
            ("l", "Liter"),
            ("m", "Meter"),
        ],
    )

    quantity_requested = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    quantity_reserved = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    quantity_shortage = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_shortage__gt=0),
                name="pri_shortage_positive",
            ),
            models.CheckConstraint(
                condition=Q(quantity_reserved__gte=0),
                name="pri_reserved_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(
                    quantity_shortage=(
                        F("quantity_requested") - F("quantity_reserved")
                    )
                ),
                name="pri_shortage_matches",
            ),
        ]

    def __str__(self):
        return f"{self.item_description} ({self.quantity_shortage})"


# =========================================================
# SUPPLIER
# =========================================================

class Supplier(models.Model):
    supplier_code = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        blank=True,
    )

    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="supplier_name_case_insensitive_unique",
                violation_error_message=(
                    "A supplier with this name already exists."
                ),
            ),
        ]

    def save(self, *args, **kwargs):
        self.name = " ".join(self.name.split())

        if self.pk is None and not self.supplier_code:
            with transaction.atomic():
                self.supplier_code = f"TMP-{uuid.uuid4().hex[:12]}"
                super().save(*args, **kwargs)

                self.supplier_code = f"SUP-{self.pk:04d}"

                Supplier.objects.filter(pk=self.pk).update(
                    supplier_code=self.supplier_code
                )
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.supplier_code} - {self.name}"


# =========================================================
# SUPPLIER QUOTATION
# =========================================================

class SupplierQuotation(models.Model):
    quotation_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        blank=True,
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="quotations",
    )

    purchase_request_item = models.ForeignKey(
        PurchaseRequestItem,
        on_delete=models.PROTECT,
        related_name="quotations",
    )

    quantity = models.DecimalField(
        "quoted quantity",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    total_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        editable=False,
        default=Decimal("0"),
    )

    quotation_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField()
    remarks = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="supplier_quotations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-quotation_date", "-id"]
        indexes = [
            models.Index(
                fields=["purchase_request_item", "supplier"]
            ),
            models.Index(fields=["valid_until"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="quotation_quantity_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gt=0),
                name="quotation_unit_price_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(total_price__gte=0),
                name="quotation_total_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__gte=F("quotation_date")),
                name="quotation_valid_until_after_date",
            ),
        ]

    @staticmethod
    def compute_total(quantity, unit_price):
        return (
            Decimal(quantity) * Decimal(unit_price)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @property
    def purchase_request(self):
        return self.purchase_request_item.purchase_request

    @property
    def is_expired(self):
        return self.valid_until < timezone.localdate()

    def save(self, *args, **kwargs):
        self.total_price = self.compute_total(
            self.quantity,
            self.unit_price,
        )

        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {
                *kwargs["update_fields"],
                "total_price",
            }

        if self.pk is None and not self.quotation_number:
            with transaction.atomic():
                self.quotation_number = f"TMP-{uuid.uuid4().hex[:12]}"
                super().save(*args, **kwargs)

                self.quotation_number = f"QT-{self.pk:04d}"

                SupplierQuotation.objects.filter(pk=self.pk).update(
                    quotation_number=self.quotation_number
                )
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.quotation_number} - "
            f"{self.supplier.name} - "
            f"{self.purchase_request_item.item_description}"
        )
