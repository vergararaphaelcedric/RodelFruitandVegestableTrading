
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from inventory.models import InventoryItem


class Requisition(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PARTIALLY_FULFILLED = "partially_fulfilled", "Partially fulfilled"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    requisition_number = models.CharField(
        max_length=20, unique=True, editable=False, blank=True
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requisitions",
    )

    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="requisitions",
    )

    request_date = models.DateField(default=timezone.localdate)
    purpose = models.TextField(help_text="Reason for the request.")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-request_date", "-id"]

        permissions = [
            ("approve_requisition", "Can approve or reject requisitions"),
        ]

        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["requested_by", "status"]),
            models.Index(fields=["department", "status"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is None and not self.requisition_number:
            with transaction.atomic():
                self.requisition_number = f"TMP-{uuid.uuid4().hex[:12]}"
                super().save(*args, **kwargs)

                self.requisition_number = f"REQ-{self.pk:04d}"

                Requisition.objects.filter(pk=self.pk).update(
                    requisition_number=self.requisition_number
                )
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return self.requisition_number or "New requisition"

    @property
    def latest_approval(self):
        approvals = list(self.approval_history.all())
        return approvals[-1] if approvals else None


class RequisitionItem(models.Model):
    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.CASCADE,
        related_name="items",
    )

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="requisition_lines",
        help_text="Leave empty if the item is not in inventory yet.",
    )

    item_description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Required when no inventory item is selected.",
    )

    unit_of_measure = models.CharField(
        max_length=10,
        choices=InventoryItem.Unit.choices,
        blank=True,
        help_text="Required when no inventory item is selected.",
    )

    quantity_requested = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    quantity_fulfilled = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_requested__gt=0),
                name="reqitem_quantity_requested_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(quantity_fulfilled__gte=0),
                name="reqitem_quantity_fulfilled_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(quantity_fulfilled__lte=F("quantity_requested")),
                name="reqitem_fulfilled_lte_requested",
            ),
            models.CheckConstraint(
                condition=Q(inventory_item__isnull=False)
                | ~Q(item_description=""),
                name="reqitem_has_item_or_description",
            ),
            models.UniqueConstraint(
                fields=["requisition", "inventory_item"],
                name="reqitem_unique_inventory_item_per_requisition",
            ),
        ]

    def clean(self):
        errors = {}

        if not self.inventory_item_id:
            if not self.item_description.strip():
                errors["item_description"] = (
                    "Describe the item, or select an inventory item."
                )

            if not self.unit_of_measure:
                errors["unit_of_measure"] = (
                    "Select a unit when the item is not in inventory."
                )

        if (
            self.quantity_requested is not None
            and self.quantity_fulfilled is not None
            and self.quantity_fulfilled > self.quantity_requested
        ):
            errors["quantity_fulfilled"] = (
                "Fulfilled quantity cannot exceed the requested quantity."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.inventory_item_id:
            if not self.item_description:
                self.item_description = self.inventory_item.name

            if not self.unit_of_measure:
                self.unit_of_measure = self.inventory_item.unit_of_measure

        super().save(*args, **kwargs)

    @property
    def is_custom_item(self):
        return self.inventory_item_id is None

    @property
    def quantity_outstanding(self):
        return self.quantity_requested - self.quantity_fulfilled

    @property
    def is_fully_fulfilled(self):
        return self.quantity_fulfilled >= self.quantity_requested

    def __str__(self):
        return f"{self.requisition} - {self.item_description or self.inventory_item}"


class AppendOnlyModel(models.Model):
    """History rows can be created but never changed or deleted."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionDenied(
                f"{self.__class__.__name__} records cannot be modified."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(
            f"{self.__class__.__name__} records cannot be deleted."
        )


class StatusHistory(AppendOnlyModel):
    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.PROTECT,
        related_name="status_history",
    )

    previous_status = models.CharField(
        max_length=20,
        choices=Requisition.Status.choices,
        blank=True,
        help_text="Empty for the first record (creation).",
    )

    new_status = models.CharField(
        max_length=20,
        choices=Requisition.Status.choices,
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="status_changes",
        help_text="Empty for automatic system changes.",
    )

    remarks = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "status history"
        ordering = ["changed_at", "id"]

        indexes = [
            models.Index(fields=["requisition", "changed_at"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=~Q(previous_status=F("new_status")),
                name="statushistory_status_must_change",
            ),
        ]

    def __str__(self):
        before = self.previous_status or "(new)"
        return f"{self.requisition}: {before} -> {self.new_status}"


class ApprovalHistory(AppendOnlyModel):

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.PROTECT,
        related_name="approval_history",
    )

    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approval_actions",
    )

    decision = models.CharField(
        max_length=10,
        choices=Decision.choices,
    )

    remarks = models.TextField(
        blank=True,
        help_text="Required when rejecting.",
    )

    previous_status = models.CharField(
        max_length=20,
        choices=Requisition.Status.choices,
    )

    new_status = models.CharField(
        max_length=20,
        choices=Requisition.Status.choices,
    )

    status_history = models.OneToOneField(
        StatusHistory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="approval",
    )

    acted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "approval history"
        ordering = ["acted_at", "id"]

        indexes = [
            models.Index(fields=["requisition", "acted_at"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(decision=F("new_status")),
                name="approval_decision_matches_new_status",
            ),
            models.CheckConstraint(
                condition=Q(previous_status="submitted"),
                name="approval_only_from_submitted",
            ),
            models.CheckConstraint(
                condition=Q(decision="approved") | ~Q(remarks=""),
                name="approval_rejection_needs_remarks",
            ),
        ]

    def check_authorized(self):
        approver = self.approver

        if not (
            approver.is_active
            and approver.has_perm("requisitions.approve_requisition")
        ):
            raise PermissionDenied(
                "You do not have permission to approve or reject requisitions."
            )

        if approver.pk == self.requisition.requested_by_id:
            raise PermissionDenied(
                "You cannot approve or reject your own requisition."
            )

    def clean(self):
        if (
            self.decision == self.Decision.REJECTED
            and not (self.remarks or "").strip()
        ):
            raise ValidationError(
                {
                    "remarks": (
                        "Remarks are required when rejecting a requisition."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.check_authorized()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.requisition} {self.decision} by {self.approver}"


class StockReservation(models.Model):

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"

    requisition_item = models.OneToOneField(
        RequisitionItem,
        on_delete=models.PROTECT,
        related_name="stock_reservation",
    )

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="stock_reservations",
    )

    quantity_requested = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    quantity_reserved = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    quantity_consumed = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    reserved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_reservations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

        indexes = [
            models.Index(fields=["inventory_item", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_requested__gt=0),
                name="stockreservation_requested_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(quantity_reserved__gte=0),
                name="stockreservation_reserved_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(quantity_reserved__lte=F("quantity_requested")),
                name="stockreservation_reserved_lte_requested",
            ),
            models.CheckConstraint(
                condition=Q(
                    quantity_consumed__gte=0,
                    quantity_consumed__lte=F("quantity_reserved"),
                ),
                name="stockreservation_consumed_valid",
            ),
        ]

    @property
    def remaining_reserved(self):
        return self.quantity_reserved - self.quantity_consumed

    @property
    def shortage(self):
        return self.quantity_requested - self.quantity_reserved

    @property
    def outcome(self):
        if self.quantity_reserved == 0:
            return "none"

        if self.quantity_reserved < self.quantity_requested:
            return "partial"

        return "sufficient"

    def __str__(self):
        return (
            f"{self.requisition_item} - "
            f"{self.quantity_reserved} reserved"
        )
