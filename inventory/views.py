
from django.db import models
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)
from django.urls import reverse, reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.http import require_POST
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    FormView,
    DetailView,
)

from receiving.models import DeliveryReceiptItem

from .forms import (
    InventoryItemForm,
    ItemCategoryForm,
    InventoryRegistrationForm,
)
from .models import (
    InventoryItem,
    ItemCategory,
    InventoryRegistration,
    Asset,
    ItemAssignment,
)
from .services import (
    register_accepted_receipt_item,
    acknowledge_item_assignment,
)


# ============================================================
# INVENTORY ITEMS
# ============================================================

class InventoryItemListView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = InventoryItem
    template_name = "inventory/item_list.html"
    context_object_name = "items"
    permission_required = "inventory.view_inventoryitem"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            InventoryItem.objects
            .select_related("category")
            .order_by("name")
        )

        search = self.request.GET.get("q", "").strip()
        category = self.request.GET.get("category", "").strip()
        stock = self.request.GET.get("stock", "").strip()
        status = self.request.GET.get("status", "active").strip()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(item_code__icontains=search)
                | Q(category__name__icontains=search)
            )

        if category:
            queryset = queryset.filter(category_id=category)

        if stock == "low":
            queryset = queryset.filter(
                quantity_on_hand__lte=models.F("reorder_level")
            )
        elif stock == "in_stock":
            queryset = queryset.filter(
                quantity_on_hand__gt=models.F("reorder_level")
            )

        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        active_items = InventoryItem.objects.filter(is_active=True)

        context.update({
            "page_title": "Inventory",
            "page_description": (
                "Manage inventory items and monitor stock levels."
            ),
            "categories": ItemCategory.objects.order_by("name"),
            "total_items": active_items.count(),
            "low_stock_count": active_items.filter(
                quantity_on_hand__lte=models.F("reorder_level")
            ).count(),
            "equipment_count": active_items.filter(
                is_durable_equipment=True
            ).count(),
            "search_query": self.request.GET.get("q", ""),
            "selected_category": self.request.GET.get("category", ""),
            "selected_stock": self.request.GET.get("stock", ""),
            "selected_status": self.request.GET.get("status", "active"),
        })

        return context


class InventoryItemCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    CreateView,
):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/item_form.html"
    permission_required = "inventory.add_inventoryitem"
    success_url = reverse_lazy("inventory-item-list")

    def form_valid(self, form):
        messages.success(
            self.request,
            "Inventory item added successfully.",
        )
        return super().form_valid(form)


class InventoryItemUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UpdateView,
):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/item_form.html"
    permission_required = "inventory.change_inventoryitem"
    success_url = reverse_lazy("inventory-item-list")

    def get_queryset(self):
        return InventoryItem.objects.select_related("category")

    def form_valid(self, form):
        messages.success(
            self.request,
            "Inventory item updated successfully.",
        )
        return super().form_valid(form)


# ============================================================
# ITEM CATEGORIES
# ============================================================

class ItemCategoryListView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = ItemCategory
    template_name = "inventory/category_list.html"
    context_object_name = "categories"
    permission_required = "inventory.view_itemcategory"
    paginate_by = 10

    def get_queryset(self):
        return ItemCategory.objects.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Item Categories"
        return context


class ItemCategoryCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    CreateView,
):
    model = ItemCategory
    form_class = ItemCategoryForm
    template_name = "inventory/category_form.html"
    permission_required = "inventory.add_itemcategory"
    success_url = reverse_lazy("inventory-category-list")

    def form_valid(self, form):
        messages.success(
            self.request,
            "Category added successfully.",
        )
        return super().form_valid(form)


class ItemCategoryUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UpdateView,
):
    model = ItemCategory
    form_class = ItemCategoryForm
    template_name = "inventory/category_form.html"
    permission_required = "inventory.change_itemcategory"
    success_url = reverse_lazy("inventory-category-list")

    def form_valid(self, form):
        messages.success(
            self.request,
            "Category updated successfully.",
        )
        return super().form_valid(form)


# ============================================================
# INVENTORY REGISTRATION
# ============================================================

class PendingInventoryRegistrationView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = DeliveryReceiptItem
    template_name = "inventory/registration_queue.html"
    context_object_name = "receipt_items"
    permission_required = "inventory.view_inventoryregistration"

    def get_queryset(self):
        return (
            DeliveryReceiptItem.objects
            .filter(
                accepted_quantity__gt=0,
                inventory_item__isnull=True,
                registration_status=(
                    DeliveryReceiptItem.RegistrationStatus
                    .AWAITING_ITEM_SETUP
                ),
                registered_quantity=0,
            )
            .select_related(
                "receipt",
                "receipt__purchase_order",
                "purchase_order_item",
            )
            .order_by("receipt__received_at", "pk")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            "page_title": "Pending Inventory Registration",
            "page_description": (
                "Register accepted deliveries that still need an "
                "inventory item assigned."
            ),
        })

        return context


class InventoryRegistrationCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    FormView,
):
    template_name = "inventory/registration_form.html"
    form_class = InventoryRegistrationForm
    permission_required = "inventory.add_inventoryregistration"

    def dispatch(self, request, *args, **kwargs):
        self.receipt_item = get_object_or_404(
            DeliveryReceiptItem.objects.select_related(
                "receipt",
                "receipt__purchase_order",
                "purchase_order_item",
            ),
            pk=kwargs["receipt_item_id"],
        )

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            "receipt_item": self.receipt_item,
            "page_title": "Register Accepted Item",
            "page_description": (
                "Assign the accepted delivery quantity to inventory."
            ),
        })

        return context

    def form_valid(self, form):
        existing_item = form.cleaned_data["inventory_item"]
        new_item_data = None

        if form.cleaned_data["create_new_item"]:
            new_item_data = {
                "name": form.cleaned_data["name"].strip(),
                "item_code": form.cleaned_data["item_code"].strip(),
                "category": form.cleaned_data["category"],
                "description": form.cleaned_data["description"],
                "unit_of_measure": (
                    form.cleaned_data["unit_of_measure"]
                ),
                "reorder_level": form.cleaned_data["reorder_level"],
                "is_durable_equipment": (
                    form.cleaned_data["is_durable_equipment"]
                ),
                "is_active": True,
            }

        try:
            registration = register_accepted_receipt_item(
                user=self.request.user,
                receipt_item_id=self.receipt_item.pk,
                inventory_item_id=(
                    existing_item.pk if existing_item else None
                ),
                new_item_data=new_item_data,
            )

        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        messages.success(
            self.request,
            (
                f"{registration.quantity} accepted units of "
                f"{registration.inventory_item.name} "
                f"were registered successfully."
            ),
        )

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("inventory-registration-queue")


class InventoryRegistrationHistoryView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = InventoryRegistration
    template_name = "inventory/registration_history.html"
    context_object_name = "registrations"
    permission_required = "inventory.view_inventoryregistration"
    paginate_by = 15

    def get_queryset(self):
        return (
            InventoryRegistration.objects
            .select_related(
                "receipt_item",
                "receipt_item__receipt",
                "receipt_item__receipt__purchase_order",
                "inventory_item",
                "ledger_entry",
                "registered_by",
            )
            .order_by("-registered_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            "page_title": "Inventory Registration History",
            "page_description": (
                "Review accepted delivery quantities registered "
                "into inventory."
            ),
        })

        return context


# ============================================================
# DAY 17: ASSET TRACKING
# ============================================================

class AssetListView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = Asset
    template_name = "inventory/asset_list.html"
    context_object_name = "assets"
    permission_required = "inventory.view_asset"
    paginate_by = 15

    def get_queryset(self):
        queryset = (
            Asset.objects
            .select_related("inventory_item")
            .order_by("asset_tag")
        )

        search = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()

        if search:
            queryset = queryset.filter(
                Q(asset_tag__icontains=search)
                | Q(serial_number__icontains=search)
                | Q(inventory_item__name__icontains=search)
                | Q(inventory_item__item_code__icontains=search)
            )

        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            "page_title": "Assets",
            "page_description": (
                "Track durable equipment and its asset tags."
            ),
            "search_query": self.request.GET.get("q", ""),
            "selected_status": self.request.GET.get("status", ""),
        })

        return context


class AssetDetailView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    DetailView,
):
    model = Asset
    template_name = "inventory/asset_detail.html"
    context_object_name = "asset"
    permission_required = "inventory.view_asset"

    def get_queryset(self):
        return Asset.objects.select_related(
            "inventory_item",
            "assignment",
            "assignment__assigned_to",
            "assignment__requisition_item",
            "assignment__requisition_item__requisition",
        )


# ============================================================
# DAY 17: ITEM ASSIGNMENTS
# ============================================================

class AssignmentListView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = ItemAssignment
    template_name = "inventory/assignment_list.html"
    context_object_name = "assignments"
    permission_required = "inventory.view_itemassignment"
    paginate_by = 15

    def get_queryset(self):
        return (
            ItemAssignment.objects
            .select_related(
                "inventory_item",
                "asset",
                "assigned_to",
                "issued_by",
                "requisition_item",
                "requisition_item__requisition",
            )
            .order_by("-issued_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            "page_title": "Item Assignments",
            "page_description": (
                "Review issued items and acknowledgement status."
            ),
        })

        return context


class MyItemsView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    ListView,
):
    model = ItemAssignment
    template_name = "inventory/my_items.html"
    context_object_name = "assignments"
    permission_required = "inventory.view_itemassignment"
    paginate_by = 15

    def get_queryset(self):
        return (
            ItemAssignment.objects
            .filter(assigned_to=self.request.user)
            .select_related(
                "inventory_item",
                "asset",
                "issued_by",
                "requisition_item",
                "requisition_item__requisition",
            )
            .order_by("-issued_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            "page_title": "My Items",
            "page_description": (
                "View items issued to you and acknowledge receipt."
            ),
        })

        return context


# ============================================================
# DAY 17: EMPLOYEE ITEM ACKNOWLEDGEMENT
# ============================================================

@login_required
@require_POST
def acknowledge_assignment(request, pk):
    try:
        acknowledge_item_assignment(
            user=request.user,
            assignment_id=pk,
            acknowledgement_note=request.POST.get(
                "acknowledgement_note",
                "",
            ).strip(),
        )

    except (PermissionDenied, ValidationError) as error:
        messages.error(request, str(error))
        return redirect("inventory-my-items")

    messages.success(
        request,
        "Item acknowledgement recorded successfully.",
    )

    return redirect("inventory-my-items")
