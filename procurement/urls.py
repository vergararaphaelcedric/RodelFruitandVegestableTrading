
from django.urls import path

from . import budget_views, purchasing_views
from .views import (
    PurchaseRequestListView,
    PurchaseRequestUpdateView,
    SupplierListView,
    SupplierCreateView,
    SupplierUpdateView,
    SupplierDeleteView,
    SupplierQuotationListView,
    SupplierQuotationCreateView,
    SupplierQuotationUpdateView,
    SupplierQuotationDeleteView,
    SupplierQuotationCompareView,
)

app_name = "procurement"

urlpatterns = [
    # Purchase Requests
    path(
        "purchase-requests/",
        PurchaseRequestListView.as_view(),
        name="purchase-request-list",
    ),
    path(
        "purchase-requests/<int:pk>/update/",
        PurchaseRequestUpdateView.as_view(),
        name="purchase-request-update",
    ),
    path(
        "purchase-requests/<int:pk>/",
        purchasing_views.PurchaseRequestReviewView.as_view(),
        name="purchase-request-detail",
    ),
    path(
        "purchase-requests/<int:pk>/submit-budget/",
        purchasing_views.PurchaseRequestSubmitBudgetView.as_view(),
        name="purchase-request-submit-budget",
    ),
    path(
        "purchase-requests/<int:pk>/generate-orders/",
        purchasing_views.PurchaseRequestGenerateOrdersView.as_view(),
        name="purchase-request-generate-orders",
    ),

    # Suppliers
    path(
        "suppliers/",
        SupplierListView.as_view(),
        name="supplier-list",
    ),
    path(
        "suppliers/add/",
        SupplierCreateView.as_view(),
        name="supplier-create",
    ),
    path(
        "suppliers/<int:pk>/edit/",
        SupplierUpdateView.as_view(),
        name="supplier-update",
    ),
    path(
        "suppliers/<int:pk>/delete/",
        SupplierDeleteView.as_view(),
        name="supplier-delete",
    ),

    # Supplier Quotations
    path(
        "quotations/",
        SupplierQuotationListView.as_view(),
        name="quotation-list",
    ),
    path(
        "quotations/add/",
        SupplierQuotationCreateView.as_view(),
        name="quotation-create",
    ),
    path(
        "quotations/<int:pk>/edit/",
        SupplierQuotationUpdateView.as_view(),
        name="quotation-update",
    ),
    path(
        "quotations/<int:pk>/delete/",
        SupplierQuotationDeleteView.as_view(),
        name="quotation-delete",
    ),

    # Supplier Quotation Comparison
    path(
        "quotation-comparison/<int:purchase_request_item_id>/",
        SupplierQuotationCompareView.as_view(),
        name="quotation-compare",
    ),

    # Budget Approvals
    path(
        "budget-approvals/",
        budget_views.BudgetListView.as_view(),
        name="budget-list",
    ),
    path(
        "budget-approvals/<int:pk>/",
        budget_views.BudgetReviewView.as_view(),
        name="budget-review",
    ),

    # Purchase Orders
    path(
        "purchase-orders/",
        purchasing_views.PurchaseOrderListView.as_view(),
        name="po-list",
    ),
    path(
        "purchase-orders/<int:pk>/",
        purchasing_views.PurchaseOrderDetailView.as_view(),
        name="po-detail",
    ),
    path(
        "purchase-orders/<int:pk>/edit/",
        purchasing_views.PurchaseOrderUpdateView.as_view(),
        name="po-edit",
    ),
    path(
        "purchase-orders/<int:pk>/issue/",
        purchasing_views.PurchaseOrderIssueView.as_view(),
        name="po-issue",
    ),
    path(
        "purchase-orders/<int:pk>/print/",
        purchasing_views.PurchaseOrderPrintView.as_view(),
        name="po-print",
    ),
]
