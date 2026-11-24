
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from .comparison import build_comparison
from .forms import PurchaseOrderFilterForm, PurchaseOrderForm
from .models import PurchaseOrder, PurchaseRequest
from .purchasing import (
    generate_purchase_orders,
    issue_purchase_order,
    submit_for_budget_approval,
)
from .views import FilteredListMixin, FormPageMixin

PR = PurchaseRequest.Status


def _msg(exc):
    return "; ".join(exc.messages)


# =========================================================
# PURCHASE REQUEST REVIEW
# =========================================================

class PurchaseRequestReviewView(PermissionRequiredMixin, View):
    """Purchase request review: pick a quotation per item and submit for budget approval."""

    permission_required = (
        "procurement.view_purchaserequest",
        "procurement.view_supplierquotation",
    )

    template_name = "procurement/purchase_request_review.html"

    def get(self, request, pk):
        purchase = get_object_or_404(
            PurchaseRequest.objects.select_related(
                "requisition__requested_by",
                "requisition__department",
            ),
            pk=pk,
        )

        comparison = build_comparison(purchase)

        for line in comparison["lines"]:
            line["default"] = (
                line["best"]["quote"].pk if line["best"] else None
            )

        approvals = list(
            purchase.budget_approvals.select_related(
                "requested_by",
                "decided_by",
            )
        )

        current = (
            approvals[0]
            if approvals and approvals[0].status != "rejected"
            else None
        )

        orders = list(
            purchase.purchase_orders.select_related("supplier").order_by("pk")
        )

        user = request.user

        return render(
            request,
            self.template_name,
            {
                "purchase": purchase,
                "comparison": comparison,
                "approvals": approvals,
                "current_approval": current,
                "orders": orders,
                "can_select": (
                    purchase.status == PR.PENDING
                    and user.has_perm(
                        "procurement.change_purchaserequest"
                    )
                ),
                "ready": (
                    bool(comparison["lines"])
                    and all(
                        line["best"]
                        for line in comparison["lines"]
                    )
                ),
                "can_generate": (
                    purchase.status == PR.BUDGET_APPROVED
                    and not orders
                    and user.has_perm(
                        "procurement.add_purchaseorder"
                    )
                ),
                "title": f"Review {purchase.request_number}",
                "eyebrow": "Purchase requests",
            },
        )


# =========================================================
# SUBMIT BUDGET FOR APPROVAL
# =========================================================

class PurchaseRequestSubmitBudgetView(PermissionRequiredMixin, View):
    permission_required = "procurement.change_purchaserequest"

    def post(self, request, pk):
        purchase = get_object_or_404(
            PurchaseRequest,
            pk=pk,
        )

        selections = {}

        for key, value in request.POST.items():
            if (
                key.startswith("quote_")
                and key[6:].isdigit()
                and value.isdigit()
            ):
                selections[int(key[6:])] = int(value)

        try:
            approval = submit_for_budget_approval(
                purchase,
                selections,
                request.user,
                request.POST.get("notes", ""),
            )

        except ValidationError as exc:
            messages.error(request, _msg(exc))

        else:
            messages.success(
                request,
                f"Budget approval requested for "
                f"{purchase.request_number} "
                f"(total {approval.total_amount:,.2f}). "
                "A manager must approve it before purchase "
                "orders can be generated.",
            )

        return redirect(
            "procurement:purchase-request-detail",
            pk=purchase.pk,
        )


# =========================================================
# GENERATE PURCHASE ORDERS
# =========================================================

class PurchaseRequestGenerateOrdersView(
    PermissionRequiredMixin,
    View,
):
    permission_required = "procurement.add_purchaseorder"

    def post(self, request, pk):
        purchase = get_object_or_404(
            PurchaseRequest,
            pk=pk,
        )

        try:
            orders = generate_purchase_orders(
                purchase,
                request.user,
            )

        except ValidationError as exc:
            messages.error(request, _msg(exc))

        else:
            numbers = ", ".join(
                order.po_number for order in orders
            )

            messages.success(
                request,
                f"Generated {numbers} as draft. "
                "Review and issue each one.",
            )

        return redirect(
            "procurement:purchase-request-detail",
            pk=purchase.pk,
        )


# =========================================================
# PURCHASE ORDER LIST
# =========================================================

class PurchaseOrderListView(
    PermissionRequiredMixin,
    FilteredListMixin,
    ListView,
):
    permission_required = "procurement.view_purchaseorder"

    template_name = "procurement/purchase_order_list.html"

    context_object_name = "orders"

    filter_form_class = PurchaseOrderFilterForm

    def get_queryset(self):
        qs = PurchaseOrder.objects.select_related(
            "supplier",
            "purchase_request__requisition",
        )

        filters = self.get_filters()

        if filters.get("q"):
            q = filters["q"]

            qs = qs.filter(
                Q(po_number__icontains=q)
                | Q(supplier_name__icontains=q)
                | Q(
                    purchase_request__request_number__icontains=q
                )
                | Q(
                    purchase_request__requisition__requisition_number__icontains=q
                )
            )

        if filters.get("status"):
            qs = qs.filter(
                status=filters["status"]
            )

        return qs


# =========================================================
# PURCHASE ORDER DETAIL
# =========================================================

class PurchaseOrderDetailView(
    PermissionRequiredMixin,
    DetailView,
):
    permission_required = "procurement.view_purchaseorder"

    template_name = "procurement/purchase_order_detail.html"

    context_object_name = "po"

    queryset = PurchaseOrder.objects.select_related(
        "supplier",
        "created_by",
        "issued_by",
        "purchase_request__requisition__requested_by",
        "purchase_request__requisition__department",
        "budget_approval__decided_by",
        "budget_approval__requested_by",
    ).prefetch_related(
        "items"
    )


# =========================================================
# PURCHASE ORDER PRINT
# =========================================================

class PurchaseOrderPrintView(PurchaseOrderDetailView):
    template_name = "procurement/purchase_order_print.html"


# =========================================================
# PURCHASE ORDER UPDATE
# =========================================================

class PurchaseOrderUpdateView(
    PermissionRequiredMixin,
    SuccessMessageMixin,
    FormPageMixin,
    UpdateView,
):
    permission_required = "procurement.change_purchaseorder"

    form_class = PurchaseOrderForm

    template_name = "procurement/purchase_order_form.html"

    eyebrow = "Purchase orders"

    success_message = "Purchase order updated."

    def get_queryset(self):
        # Only draft purchase orders can be edited.
        return PurchaseOrder.objects.filter(
            status=PurchaseOrder.Status.DRAFT
        )

    @property
    def title(self):
        return f"Edit {self.object.po_number}"

    def get_success_url(self):
        return reverse(
            "procurement:po-detail",
            args=[self.object.pk],
        )

    def get_cancel_url(self):
        return reverse(
            "procurement:po-detail",
            args=[self.object.pk],
        )


# =========================================================
# ISSUE PURCHASE ORDER
# =========================================================

class PurchaseOrderIssueView(
    PermissionRequiredMixin,
    View,
):
    permission_required = "procurement.change_purchaseorder"

    def post(self, request, pk):
        po = get_object_or_404(
            PurchaseOrder,
            pk=pk,
        )

        try:
            issue_purchase_order(
                po,
                request.user,
            )

        except ValidationError as exc:
            messages.error(request, _msg(exc))

        else:
            messages.success(
                request,
                f"{po.po_number} was issued.",
            )

        return redirect(
            "procurement:po-detail",
            pk=po.pk,
        )
