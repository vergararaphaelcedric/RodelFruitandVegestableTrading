
from django.contrib import admin

from .models import (
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierQuotation,
)


class PurchaseRequestItemInline(admin.TabularInline):
    model = PurchaseRequestItem
    extra = 0
    can_delete = False
    show_change_link = False

    fields = (
        "requisition_item",
        "inventory_item",
        "item_description",
        "unit_of_measure",
        "quantity_requested",
        "quantity_reserved",
        "quantity_shortage",
    )

    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = (
        "request_number",
        "requisition",
        "status",
        "created_by",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "request_number",
        "requisition__requisition_number",
        "created_by__username",
    )

    readonly_fields = (
        "request_number",
        "requisition",
        "created_by",
        "created_at",
        "updated_at",
    )

    fields = (
        "request_number",
        "requisition",
        "status",
        "created_by",
        "notes",
        "created_at",
        "updated_at",
    )

    inlines = [PurchaseRequestItemInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "supplier_code",
        "name",
        "contact_person",
        "email",
        "phone",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "supplier_code",
        "name",
        "contact_person",
        "email",
        "phone",
    )

    readonly_fields = (
        "supplier_code",
        "created_at",
        "updated_at",
    )

    ordering = ("name",)


@admin.register(SupplierQuotation)
class SupplierQuotationAdmin(admin.ModelAdmin):
    list_display = (
        "quotation_number",
        "supplier",
        "purchase_request_item",
        "quantity",
        "unit_price",
        "total_price",
        "quotation_date",
        "valid_until",
    )

    list_filter = (
        "quotation_date",
        "valid_until",
        "supplier",
    )

    search_fields = (
        "quotation_number",
        "supplier__name",
        "purchase_request_item__item_description",
    )

    readonly_fields = (
        "quotation_number",
        "total_price",
    )

    ordering = ("-quotation_date",)
