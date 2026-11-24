
from django.urls import path

from . import views

app_name = "receiving"

urlpatterns = [
    path(
        "expected-deliveries/",
        views.ExpectedDeliveriesView.as_view(),
        name="expected-deliveries",
    ),
    path(
        "purchase-order/<int:pk>/verify/",
        views.PurchaseOrderVerificationView.as_view(),
        name="purchase-order-verification",
    ),
    path(
        "purchase-order/<int:pk>/record-delivery/",
        views.DeliveryReceiptCreateView.as_view(),
        name="record-delivery",
    ),
    path(
        "discrepancies/",
        views.DiscrepancyListView.as_view(),
        name="discrepancy-list",
    ),
    path(
        "discrepancies/<int:pk>/update/",
        views.DiscrepancyUpdateView.as_view(),
        name="discrepancy-update",
    ),
]
