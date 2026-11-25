
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
    AssetListView,
    AssetDetailView,
    AssignmentListView,
    MyItemsView,
    acknowledge_assignment,
)

from .issuance_views import fulfil_requisitions


urlpatterns = [
    path(
        "",
        InventoryItemListView.as_view(),
        name="inventory-item-list",
    ),

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

    path(
        "assets/",
        AssetListView.as_view(),
        name="inventory-asset-list",
    ),
    path(
        "assets/<int:pk>/",
        AssetDetailView.as_view(),
        name="inventory-asset-detail",
    ),

    path(
        "assignments/",
        AssignmentListView.as_view(),
        name="inventory-assignment-list",
    ),
    path(
        "my-items/",
        MyItemsView.as_view(),
        name="inventory-my-items",
    ),
    path(
        "assignments/<int:pk>/acknowledge/",
        acknowledge_assignment,
        name="inventory-acknowledge-assignment",
    ),

    path(
        "fulfil-requisitions/",
        fulfil_requisitions,
        name="inventory-fulfil-requisitions",
    ),
]
