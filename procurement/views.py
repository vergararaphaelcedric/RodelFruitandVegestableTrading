
from django.contrib import messages
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UserPassesTestMixin,
)
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from accounts.models import User

from .forms import (
    PurchaseRequestUpdateForm,
    SupplierForm,
    SupplierQuotationForm,
)

from .models import (
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierQuotation,
)


# =========================================================
# SHARED PROCUREMENT VIEW MIXINS
# =========================================================

class FilteredListMixin:
    """Provides validated GET filters to procurement list views."""

    filter_form_class = None

    def get_filters(self):
        if self.filter_form_class is None:
            return {}

        form = self.filter_form_class(self.request.GET)

        if form.is_valid():
            return form.cleaned_data

        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.filter_form_class is not None:
            context["filter_form"] = self.filter_form_class(
                self.request.GET
            )

        return context


class FormPageMixin:
    """Provides shared page context for procurement forms."""

    eyebrow = "Procurement"

    @property
    def title(self):
        return "Procurement Form"

    def get_cancel_url(self):
        return "/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["page_title"] = self.title
        context["eyebrow"] = self.eyebrow
        context["submit_label"] = "Save Changes"
        context["cancel_url"] = self.get_cancel_url()

        return context

class PurchaseRequestListView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = PurchaseRequest
    template_name = "procurement/purchase_request_list.html"
    context_object_name = "purchase_requests"
    permission_required = "procurement.view_purchaserequest"

    def get_queryset(self):
        return PurchaseRequest.objects.select_related(
            "requisition",
            "requisition__requested_by",
            "requisition__department",
            "created_by",
        ).order_by("-created_at", "-pk")
# =========================================================
# PURCHASE REQUEST MANAGEMENT
# =========================================================

class PurchaseRequestUpdateView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    UpdateView,
):
    model = PurchaseRequest
    form_class = PurchaseRequestUpdateForm
    template_name = "procurement/purchase_request_update.html"
    pk_url_kwarg = "pk"

    def test_func(self):
        user = self.request.user

        return (
            user.is_authenticated
            and user.is_active
            and user.role == User.Role.PURCHASING_STAFF
            and user.has_perm("procurement.change_purchaserequest")
        )

    def get_queryset(self):
        return PurchaseRequest.objects.select_related(
            "requisition",
            "created_by",
        ).prefetch_related("items")

    def form_valid(self, form):
        with transaction.atomic():
            purchase_request = form.save()

        messages.success(
            self.request,
            f"Purchase Request {purchase_request.request_number} "
            "was updated successfully.",
        )

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("dashboard-purchasing")


# =========================================================
# SUPPLIER MANAGEMENT
# =========================================================

class SupplierListView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = Supplier
    template_name = "procurement/supplier_list.html"
    context_object_name = "suppliers"
    permission_required = "procurement.view_supplier"

    def get_queryset(self):
        return Supplier.objects.all().order_by("name")


class SupplierCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    CreateView,
):
    model = Supplier
    form_class = SupplierForm
    template_name = "procurement/supplier_form.html"
    permission_required = "procurement.add_supplier"
    success_url = reverse_lazy("procurement:supplier-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Supplier"
        context["submit_label"] = "Create Supplier"
        context["cancel_url"] = self.success_url
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.success(
            self.request,
            f"Supplier {self.object.name} was created successfully.",
        )

        return response


class SupplierUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UpdateView,
):
    model = Supplier
    form_class = SupplierForm
    template_name = "procurement/supplier_form.html"
    permission_required = "procurement.change_supplier"
    success_url = reverse_lazy("procurement:supplier-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Update Supplier"
        context["submit_label"] = "Save Changes"
        context["cancel_url"] = self.success_url
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.success(
            self.request,
            f"Supplier {self.object.name} was updated successfully.",
        )

        return response


class SupplierDeleteView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    DeleteView,
):
    model = Supplier
    template_name = "procurement/supplier_confirm_delete.html"
    permission_required = "procurement.delete_supplier"
    success_url = reverse_lazy("procurement:supplier-list")

    def form_valid(self, form):
        supplier_name = self.object.name

        try:
            response = super().form_valid(form)

            messages.success(
                self.request,
                f"Supplier {supplier_name} was deleted successfully.",
            )

            return response

        except ProtectedError:
            self.object.is_active = False
            self.object.save(update_fields=["is_active"])

            messages.warning(
                self.request,
                f"{supplier_name} has existing quotations and "
                "was deactivated instead of deleted.",
            )

            return redirect(self.success_url)


# =========================================================
# SELECTED QUOTATION LOCK
# =========================================================

class SelectedQuotationLockMixin:
    """A selected quotation cannot be changed or deleted."""

    def dispatch(self, request, *args, **kwargs):
        quote = get_object_or_404(
            SupplierQuotation,
            pk=kwargs["pk"],
        )

        if request.user.is_authenticated and quote.selected_for.exists():
            messages.error(
                request,
                f"{quote.quotation_number} was selected for a "
                "purchase request and is locked.",
            )
            return redirect("procurement:quotation-list")

        return super().dispatch(request, *args, **kwargs)


# =========================================================
# SUPPLIER QUOTATION MANAGEMENT
# =========================================================

class SupplierQuotationListView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = SupplierQuotation
    template_name = "procurement/supplier_quotation_list.html"
    context_object_name = "quotations"
    permission_required = "procurement.view_supplierquotation"

    def get_queryset(self):
        return SupplierQuotation.objects.select_related(
            "supplier",
            "purchase_request_item",
            "purchase_request_item__purchase_request",
        ).order_by(
            "-quotation_date",
            "-created_at",
        )


class SupplierQuotationCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    CreateView,
):
    model = SupplierQuotation
    form_class = SupplierQuotationForm
    template_name = "procurement/supplier_quotation_form.html"
    permission_required = "procurement.add_supplierquotation"
    success_url = reverse_lazy("procurement:quotation-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Supplier Quotation"
        context["submit_label"] = "Save Quotation"
        context["cancel_url"] = self.success_url
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user

        response = super().form_valid(form)

        messages.success(
            self.request,
            f"Quotation {self.object.quotation_number} "
            "was recorded successfully.",
        )

        return response


class SupplierQuotationUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SelectedQuotationLockMixin,
    UpdateView,
):
    model = SupplierQuotation
    form_class = SupplierQuotationForm
    template_name = "procurement/supplier_quotation_form.html"
    permission_required = "procurement.change_supplierquotation"
    success_url = reverse_lazy("procurement:quotation-list")

    def get_queryset(self):
        return SupplierQuotation.objects.select_related(
            "supplier",
            "purchase_request_item",
            "created_by",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Update Supplier Quotation"
        context["submit_label"] = "Save Changes"
        context["cancel_url"] = self.success_url
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.success(
            self.request,
            f"Quotation {self.object.quotation_number} "
            "was updated successfully.",
        )

        return response


class SupplierQuotationDeleteView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SelectedQuotationLockMixin,
    DeleteView,
):
    model = SupplierQuotation
    template_name = (
        "procurement/supplier_quotation_confirm_delete.html"
    )
    permission_required = "procurement.delete_supplierquotation"
    success_url = reverse_lazy("procurement:quotation-list")

    def form_valid(self, form):
        quotation_number = self.object.quotation_number

        response = super().form_valid(form)

        messages.success(
            self.request,
            f"Quotation {quotation_number} was deleted successfully.",
        )

        return response


# =========================================================
# SUPPLIER QUOTATION COMPARISON
# =========================================================

class SupplierQuotationCompareView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    DetailView,
):
    model = PurchaseRequestItem
    template_name = "procurement/supplier_quotation_compare.html"
    context_object_name = "purchase_request_item"
    pk_url_kwarg = "purchase_request_item_id"
    permission_required = "procurement.view_supplierquotation"

    def get_queryset(self):
        return PurchaseRequestItem.objects.select_related(
            "purchase_request",
            "requisition_item",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        quotations = SupplierQuotation.objects.filter(
            purchase_request_item=self.object
        ).select_related(
            "supplier",
        ).order_by(
            "unit_price",
            "quotation_date",
        )

        context["quotations"] = quotations
        context["quotation_count"] = quotations.count()
        context["best_quotation"] = quotations.first()

        return context
