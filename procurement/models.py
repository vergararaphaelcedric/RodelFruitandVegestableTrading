
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from inventory.models import InventoryItem


# =========================================================
# PURCHASE REQUEST
# =========================================================

class PurchaseRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        BUDGET_REVIEW = "budget_review", "Awaiting budget approval"
        BUDGET_APPROVED = "budget_approved", "Budget approved"
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

    selected_quotation = models.ForeignKey(
        "SupplierQuotation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="selected_for",
        help_text="The quotation chosen for budget approval. Locks that quotation.",
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


# =========================================================
# BUDGET APPROVAL
# =========================================================

class BudgetApproval(models.Model):
    """A request for the manager to approve the budget for selected quotations."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.PROTECT,
        related_name="budget_approvals",
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="budget_requests",
    )

    request_notes = models.TextField(blank=True)

    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    snapshot = models.JSONField(
        default=list,
        help_text="The selected lines as they were submitted.",
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="budget_decisions",
    )

    remarks = models.TextField(
        blank=True,
        help_text="Required when rejecting.",
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at", "-id"]
        permissions = [
            ("approve_budget", "Can approve or reject purchase budgets")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_amount__gt=0),
                name="budget_total_gt_0",
            ),
            models.UniqueConstraint(
                fields=["purchase_request"],
                condition=Q(status="pending"),
                name="budget_one_pending_per_request",
            ),
            models.UniqueConstraint(
                fields=["purchase_request"],
                condition=Q(status="approved"),
                name="budget_one_approved_per_request",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="pending")
                    & Q(decided_by__isnull=True)
                    & Q(decided_at__isnull=True)
                )
                | (
                    ~Q(status="pending")
                    & Q(decided_by__isnull=False)
                    & Q(decided_at__isnull=False)
                ),
                name="budget_decision_fields_match_status",
            ),
            models.CheckConstraint(
                condition=~Q(status="rejected") | ~Q(remarks=""),
                name="budget_rejection_needs_remarks",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            current = (
                BudgetApproval.objects
                .filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )

            if current != self.Status.PENDING:
                raise PermissionDenied(
                    "A decided budget approval cannot be changed."
                )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Budget approvals cannot be deleted.")

    def __str__(self):
        return f"Budget for {self.purchase_request} ({self.status})"


# =========================================================
# PURCHASE ORDER
# =========================================================

class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"

    po_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        blank=True,
    )

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )

    budget_approval = models.ForeignKey(
        BudgetApproval,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )

    # Supplier details are copied so the printed PO never changes after it is issued.
    supplier_name = models.CharField(max_length=200)
    supplier_address = models.TextField(blank=True)
    supplier_contact = models.CharField(max_length=150, blank=True)
    supplier_email = models.EmailField(blank=True)
    supplier_phone = models.CharField(max_length=30, blank=True)
    payment_terms = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    order_date = models.DateField(default=timezone.localdate)
    expected_delivery_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_orders_created",
    )

    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_orders_issued",
    )

    issued_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "created_at"])
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_amount__gte=0),
                name="po_total_gte_0",
            ),
            models.UniqueConstraint(
                fields=["purchase_request", "supplier"],
                name="po_one_per_supplier_per_request",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="draft") & Q(issued_at__isnull=True)
                )
                | (
                    Q(status="issued")
                    & Q(issued_at__isnull=False)
                    & Q(issued_by__isnull=False)
                ),
                name="po_issued_fields_match_status",
            ),
            models.CheckConstraint(
                condition=Q(expected_delivery_date__isnull=True)
                | Q(expected_delivery_date__gte=F("order_date")),
                name="po_delivery_not_before_order",
            ),
        ]

    @property
    def is_draft(self):
        return self.status == self.Status.DRAFT

    def save(self, *args, **kwargs):
        # No purchase order can be created or changed without an approved budget.
        if self.budget_approval.status != BudgetApproval.Status.APPROVED:
            raise PermissionDenied(
                "A purchase order requires an approved budget."
            )

        if self.pk is None and not self.po_number:
            with transaction.atomic():
                self.po_number = f"TMP-{uuid.uuid4().hex[:12]}"
                super().save(*args, **kwargs)

                self.po_number = f"PO-{self.pk:04d}"

                PurchaseOrder.objects.filter(pk=self.pk).update(
                    po_number=self.po_number
                )
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return self.po_number or "New purchase order"


# =========================================================
# PURCHASE ORDER ITEM
# =========================================================

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )

    # OneToOne: a purchase request line can be on at most one purchase order.
    purchase_request_item = models.OneToOneField(
        PurchaseRequestItem,
        on_delete=models.PROTECT,
        related_name="purchase_order_item",
    )

    quotation = models.ForeignKey(
        SupplierQuotation,
        on_delete=models.PROTECT,
        related_name="purchase_order_items",
    )

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_order_lines",
    )

    item_description = models.CharField(
        "item name",
        max_length=255,
    )

    unit_of_measure = models.CharField(
        max_length=10,
        choices=InventoryItem.Unit.choices,
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="poitem_quantity_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gt=0),
                name="poitem_unit_price_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(line_total__gte=0),
                name="poitem_total_gte_0",
            ),
        ]

    def __str__(self):
        return (
            f"{self.purchase_order} - "
            f"{self.item_description} x {self.quantity}"
        )
