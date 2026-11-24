
from django.urls import path

from .views import (
    MyRequisitionsView,
    PendingRequisitionsView,
    RequisitionCreateView,
    RequisitionDetailView,
    RequisitionReviewView,
    RequisitionTrackingView,
)

from .manager_views import (
    PendingApprovalListView,
    ApprovedRequisitionListView,
    RejectedRequisitionListView,
    ManagerApprovalHistoryView,
    ManagerRequisitionReviewView,
)

urlpatterns = [
    # Employee requisition pages
    path(
        "",
        MyRequisitionsView.as_view(),
        name="my-requisitions",
    ),
    path(
        "new/",
        RequisitionCreateView.as_view(),
        name="requisition-create",
    ),
    path(
        "<int:pk>/",
        RequisitionDetailView.as_view(),
        name="requisition-detail",
    ),
    path(
        "<int:pk>/track/",
        RequisitionTrackingView.as_view(),
        name="requisition-tracking",
    ),

    # Existing manager pages
    path(
        "pending/",
        PendingRequisitionsView.as_view(),
        name="pending-requisitions",
    ),
    path(
        "<int:pk>/review/",
        RequisitionReviewView.as_view(),
        name="requisition-review",
    ),

    # Manager approval pages
    path(
        "manager/pending/",
        PendingApprovalListView.as_view(),
        name="manager-pending",
    ),
    path(
        "manager/approved/",
        ApprovedRequisitionListView.as_view(),
        name="manager-approved",
    ),
    path(
        "manager/rejected/",
        RejectedRequisitionListView.as_view(),
        name="manager-rejected",
    ),
    path(
        "manager/history/",
        ManagerApprovalHistoryView.as_view(),
        name="manager-approval-history",
    ),
    path(
        "manager/<int:pk>/review/",
        ManagerRequisitionReviewView.as_view(),
        name="manager-review",
    ),
]
