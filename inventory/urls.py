
from django.urls import path

from .views import (
    InventoryItemListView,
    InventoryItemCreateView,
    InventoryItemUpdateView,
    ItemCategoryListView,
    ItemCategoryCreateView,
    ItemCategoryUpdateView,
    PendingInventoryRegistrationView,
    InventoryRegistrationCreateView,
    InventoryRegistrationHistoryView,
)

urlpatterns = [
    path("", InventoryItemListView.as_view(), name="inventory-item-list"),

    path(
        "items/new/",
        InventoryItemCreateView.as_view(),
        name="inventory-item-create",
    ),
    path(
        "items/<int:pk>/edit/",
        InventoryItemUpdateView.as_view(),
        name="inventory-item-update",
    ),

    path(
        "categories/",
        ItemCategoryListView.as_view(),
        name="inventory-category-list",
    ),
    path(
        "categories/new/",
        ItemCategoryCreateView.as_view(),
        name="inventory-category-create",
    ),
    path(
        "categories/<int:pk>/edit/",
        ItemCategoryUpdateView.as_view(),
        name="inventory-category-update",
    ),

    path(
        "registrations/",
        PendingInventoryRegistrationView.as_view(),
        name="inventory-registration-queue",
    ),
    path(
        "registrations/<int:receipt_item_id>/register/",
        InventoryRegistrationCreateView.as_view(),
        name="inventory-registration-create",
    ),
    path(
        "registrations/history/",
        InventoryRegistrationHistoryView.as_view(),
        name="inventory-registration-history",
    ),
]
