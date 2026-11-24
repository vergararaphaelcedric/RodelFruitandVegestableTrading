
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from procurement.models import PurchaseOrder

from .forms import (
    DeliveryReceiptForm,
    DeliveryReceiptItemFormSet,
    DeliveryDiscrepancyResolutionForm,
)
from .models import DeliveryDiscrepancy, DeliveryReceiptItem
from .services import record_delivery


class ReceivingStaffRequiredMixin(
    LoginRequiredMixin,
    UserPassesTestMixin,
):
    """Restrict receiving pages to active Receiving Staff."""

    def test_func(self):
        return (
            self.request.user.is_active
            and self.request.user.role == "receiving_staff"
        )


class ExpectedDeliveriesView(
    ReceivingStaffRequiredMixin,
    ListView,
):
    template_name = "receiving/expected_deliveries.html"
    context_object_name = "expected_deliveries"

    def get_queryset(self):
        expected_deliveries = []

        purchase_orders = (
            PurchaseOrder.objects
            .filter(status=PurchaseOrder.Status.ISSUED)
            .prefetch_related("items")
            .order_by("-issued_at")
        )

        for purchase_order in purchase_orders:
            expected_items = []

            for po_item in purchase_order.items.all():
                accepted_total = (
                    DeliveryReceiptItem.objects
                    .filter(purchase_order_item=po_item)
                    .aggregate(total=Sum("accepted_quantity"))["total"]
                    or 0
                )

                outstanding = po_item.quantity - accepted_total

                if outstanding <= 0:
                    continue

                expected_items.append({
                    "description": po_item.item_description,
                    "unit": po_item.unit_of_measure,
                    "ordered_quantity": po_item.quantity,
                    "accepted_quantity": accepted_total,
                    "outstanding_quantity": outstanding,
                })

            if expected_items:
                expected_deliveries.append({
                    "purchase_order_id": purchase_order.pk,
                    "po_number": purchase_order.po_number,
                    "supplier_name": purchase_order.supplier_name,
                    "expected_delivery_date": (
                        purchase_order.expected_delivery_date
                    ),
                    "items": expected_items,
                })

        return expected_deliveries


class PurchaseOrderVerificationView(
    ReceivingStaffRequiredMixin,
    TemplateView,
):
    template_name = "receiving/purchase_order_verification.html"

    def dispatch(self, request, *args, **kwargs):
        self.purchase_order = get_object_or_404(
            PurchaseOrder,
            pk=kwargs["pk"],
            status=PurchaseOrder.Status.ISSUED,
        )

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        purchase_order = self.purchase_order
        verified_items = []

        for po_item in purchase_order.items.all():
            accepted_total = (
                DeliveryReceiptItem.objects
                .filter(purchase_order_item=po_item)
                .aggregate(total=Sum("accepted_quantity"))["total"]
                or 0
            )

            outstanding = po_item.quantity - accepted_total

            if outstanding < 0:
                outstanding = 0

            if accepted_total >= po_item.quantity:
                item_status = "Complete"
            elif accepted_total > 0:
                item_status = "Partially Received"
            else:
                item_status = "Pending Delivery"

            verified_items.append({
                "description": po_item.item_description,
                "unit": po_item.unit_of_measure,
                "ordered_quantity": po_item.quantity,
                "accepted_quantity": accepted_total,
                "outstanding_quantity": outstanding,
                "status": item_status,
            })

        context.update({
            "purchase_order": purchase_order,
            "verified_items": verified_items,
            "total_items": len(verified_items),
            "total_outstanding": sum(
                (
                    item["outstanding_quantity"]
                    for item in verified_items
                ),
                0,
            ),
        })

        return context


class DeliveryReceiptCreateView(
    ReceivingStaffRequiredMixin,
    TemplateView,
):
    template_name = "receiving/record_delivery.html"

    def dispatch(self, request, *args, **kwargs):
        self.purchase_order = get_object_or_404(
            PurchaseOrder,
            pk=kwargs["pk"],
            status=PurchaseOrder.Status.ISSUED,
        )

        return super().dispatch(request, *args, **kwargs)

    def get_po_items(self):
        return list(
            self.purchase_order.items
            .select_related("inventory_item")
            .all()
        )

    def get_initial_item_data(self):
        initial = []

        for po_item in self.get_po_items():
            accepted_total = (
                DeliveryReceiptItem.objects
                .filter(purchase_order_item=po_item)
                .aggregate(total=Sum("accepted_quantity"))["total"]
                or 0
            )

            outstanding = po_item.quantity - accepted_total

            if outstanding > 0:
                initial.append({
                    "purchase_order_item_id": po_item.pk,
                    "delivered_quantity": 0,
                    "accepted_quantity": 0,
                    "damaged_quantity": 0,
                    "incorrect_quantity": 0,
                })

        return initial

    def build_item_rows(self, formset):
        po_items = {
            item.pk: item
            for item in self.get_po_items()
        }

        rows = []

        for form in formset.forms:
            item_id = form.initial.get("purchase_order_item_id")

            if item_id is None:
                item_id = form["purchase_order_item_id"].value()

            try:
                item_id = int(item_id)
            except (TypeError, ValueError):
                continue

            po_item = po_items.get(item_id)

            if po_item is not None:
                rows.append({
                    "item": po_item,
                    "form": form,
                })

        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        receipt_form = kwargs.get(
            "receipt_form",
            DeliveryReceiptForm(prefix="receipt"),
        )

        item_formset = kwargs.get(
            "item_formset",
            DeliveryReceiptItemFormSet(
                initial=self.get_initial_item_data(),
                prefix="items",
            ),
        )

        context.update({
            "purchase_order": self.purchase_order,
            "receipt_form": receipt_form,
            "item_formset": item_formset,
            "item_rows": self.build_item_rows(item_formset),
        })

        return context

    def post(self, request, *args, **kwargs):
        receipt_form = DeliveryReceiptForm(
            request.POST,
            prefix="receipt",
        )

        item_formset = DeliveryReceiptItemFormSet(
            request.POST,
            initial=self.get_initial_item_data(),
            prefix="items",
        )

        if receipt_form.is_valid() and item_formset.is_valid():
            submitted_items = []

            for item_data in item_formset.cleaned_data:
                submitted_items.append({
                    "purchase_order_item_id": (
                        item_data["purchase_order_item_id"]
                    ),
                    "delivered_quantity": (
                        item_data["delivered_quantity"]
                    ),
                    "accepted_quantity": (
                        item_data["accepted_quantity"]
                    ),
                    "damaged_quantity": (
                        item_data["damaged_quantity"]
                    ),
                    "incorrect_quantity": (
                        item_data["incorrect_quantity"]
                    ),
                    "damaged_description": (
                        item_data["damaged_description"]
                    ),
                    "incorrect_description": (
                        item_data["incorrect_description"]
                    ),
                })

            try:
                receipt = record_delivery(
                    user=request.user,
                    purchase_order_id=self.purchase_order.pk,
                    delivery_note_number=(
                        receipt_form.cleaned_data[
                            "delivery_note_number"
                        ]
                    ),
                    remarks=receipt_form.cleaned_data["remarks"],
                    items=submitted_items,
                )

            except ValidationError as error:
                receipt_form.add_error(
                    None,
                    " ".join(error.messages),
                )

            else:
                messages.success(
                    request,
                    (
                        f"Delivery receipt {receipt.receipt_number} "
                        "was recorded successfully."
                    ),
                )

                return redirect("receiving:expected-deliveries")

        context = self.get_context_data(
            receipt_form=receipt_form,
            item_formset=item_formset,
        )

        return self.render_to_response(context)


class DiscrepancyListView(
    ReceivingStaffRequiredMixin,
    ListView,
):
    template_name = "receiving/discrepancy_list.html"
    context_object_name = "discrepancy_records"

    def get_queryset(self):
        return (
            DeliveryDiscrepancy.objects
            .select_related(
                "receipt_item__receipt__purchase_order",
                "receipt_item__purchase_order_item",
                "reported_by",
                "resolved_by",
            )
            .order_by("-created_at")
        )


class DiscrepancyUpdateView(
    ReceivingStaffRequiredMixin,
    TemplateView,
):
    template_name = "receiving/discrepancy_update.html"

    def dispatch(self, request, *args, **kwargs):
        self.discrepancy = get_object_or_404(
            DeliveryDiscrepancy.objects.select_related(
                "receipt_item__receipt__purchase_order",
                "receipt_item__purchase_order_item",
            ),
            pk=kwargs["pk"],
        )

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            "discrepancy": self.discrepancy,
            "resolution_form": kwargs.get(
                "resolution_form",
                DeliveryDiscrepancyResolutionForm(
                    instance=self.discrepancy
                ),
            ),
        })

        return context

    def post(self, request, *args, **kwargs):
        resolution_form = DeliveryDiscrepancyResolutionForm(
            request.POST,
            instance=self.discrepancy,
        )

        if resolution_form.is_valid():
            discrepancy = resolution_form.save(commit=False)

            if (
                discrepancy.status
                == DeliveryDiscrepancy.Status.SUPPLIER_NOTIFIED
            ):
                if not discrepancy.supplier_notified_at:
                    discrepancy.supplier_notified_at = timezone.now()

            if discrepancy.status in {
                DeliveryDiscrepancy.Status.REPLACED,
                DeliveryDiscrepancy.Status.CREDITED,
                DeliveryDiscrepancy.Status.CLOSED,
            }:
                discrepancy.resolved_by = request.user
                discrepancy.resolved_at = timezone.now()

            discrepancy.save()

            messages.success(
                request,
                "Supplier resolution was updated successfully.",
            )

            return redirect("receiving:discrepancy-list")

        return self.render_to_response(
            self.get_context_data(
                resolution_form=resolution_form,
            )
        )
