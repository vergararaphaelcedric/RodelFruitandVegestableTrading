
from django.contrib import admin
from django.db import transaction

from .models import (
    InventoryItem,
    InventoryTransaction,
    ItemCategory,
)


@admin.register(ItemCategory)
class ItemCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        "item_code",
        "name",
        "category",
        "unit_of_measure",
        "quantity_on_hand",
        "quantity_reserved",
        "quantity_available_display",
        "reorder_level",
        "low_stock",
        "is_durable_equipment",
        "is_active",
    )

    list_filter = (
        "category",
        "is_durable_equipment",
        "is_active",
        "unit_of_measure",
    )

    search_fields = ("item_code", "name", "description")
    list_select_related = ("category",)

    readonly_fields = (
        "quantity_reserved",
        "quantity_available_display",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "item_code",
                    "name",
                    "category",
                    "description",
                )
            },
        ),
        (
            "Stock",
            {
                "fields": (
                    "unit_of_measure",
                    "quantity_on_hand",
                    "quantity_reserved",
                    "quantity_available_display",
                    "reorder_level",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "is_durable_equipment",
                    "is_active",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Available stock")
    def quantity_available_display(self, obj):
        return obj.quantity_available

    @admin.display(boolean=True, description="Low stock")
    def low_stock(self, obj):
        return obj.is_low_stock

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            old_quantity = None

            if change:
                old_quantity = (
                    InventoryItem.objects
                    .select_for_update()
                    .get(pk=obj.pk)
                    .quantity_on_hand
                )

            super().save_model(request, obj, form, change)

            if not change:
                quantity_change = obj.quantity_on_hand
                remarks = "Opening inventory balance."
            else:
                quantity_change = obj.quantity_on_hand - old_quantity
                remarks = "Manual stock adjustment through Django Admin."

            if quantity_change != 0:
                InventoryTransaction.record(
                    inventory_item=obj,
                    transaction_type=(
                        InventoryTransaction.TransactionType.ADJUSTMENT
                    ),
                    on_hand_change=quantity_change,
                    reserved_change=0,
                    reference=f"ADMIN:{obj.pk}",
                    remarks=remarks,
                    created_by=request.user,
                )


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "inventory_item",
        "transaction_type",
        "on_hand_change",
        "reserved_change",
        "on_hand_after",
        "reserved_after",
        "reference",
        "created_by",
    )

    list_filter = (
        "transaction_type",
        "created_at",
    )

    search_fields = (
        "inventory_item__item_code",
        "inventory_item__name",
        "reference",
        "remarks",
    )

    list_select_related = (
        "inventory_item",
        "created_by",
    )

    readonly_fields = (
        "inventory_item",
        "transaction_type",
        "on_hand_change",
        "reserved_change",
        "on_hand_after",
        "reserved_after",
        "reference",
        "remarks",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
