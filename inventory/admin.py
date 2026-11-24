from django.contrib import admin

from .models import (
    Asset,
    InventoryItem,
    InventoryRegistration,
    InventoryTransaction,
    ItemAssignment,
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
        "quantity_on_hand",
        "quantity_reserved",
        "is_durable_equipment",
        "is_active",
    )
    list_filter = ("category", "is_durable_equipment", "is_active")
    search_fields = ("item_code", "name")


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "inventory_item",
        "transaction_type",
        "on_hand_change",
        "reserved_change",
        "reference",
        "created_at",
    )
    list_filter = ("transaction_type",)
    search_fields = ("reference", "related_reference")
    readonly_fields = (
        "inventory_item",
        "transaction_type",
        "on_hand_change",
        "reserved_change",
        "on_hand_after",
        "reserved_after",
        "reference",
        "related_reference",
        "remarks",
        "created_by",
        "created_at",
    )


@admin.register(InventoryRegistration)
class InventoryRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_item",
        "inventory_item",
        "quantity",
        "item_created",
        "registered_by",
        "registered_at",
    )
    readonly_fields = (
        "receipt_item",
        "inventory_item",
        "ledger_entry",
        "quantity",
        "item_created",
        "registered_by",
        "registered_at",
    )


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "asset_tag",
        "inventory_item",
        "serial_number",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("asset_tag", "serial_number", "inventory_item__name")


@admin.register(ItemAssignment)
class ItemAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "inventory_item",
        "assigned_to",
        "quantity",
        "status",
        "issued_at",
        "acknowledged_at",
    )
    list_filter = ("status",)
    search_fields = (
        "inventory_item__name",
        "assigned_to__username",
    )
    readonly_fields = (
        "requisition_item",
        "inventory_item",
        "asset",
        "assigned_to",
        "issued_by",
        "quantity",
        "issued_at",
        "acknowledged_at",
        "status",
        "acknowledgement_note",
    )