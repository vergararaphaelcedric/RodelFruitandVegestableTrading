
from django.urls import reverse

from procurement.models import PurchaseRequest
from requisitions.models import Requisition
from inventory.models import ItemAssignment


def dashboard_ui(request):
    """Provide role-aware navigation and notifications."""

    if not request.user.is_authenticated:
        return {}

    user = request.user
    role = getattr(user, "role", "")

    sections = []

    # Main navigation
    main_items = [
        {
            "label": "Dashboard",
            "url": reverse(user.dashboard_url_name),
            "icon": "bi-speedometer2",
        },
    ]

    if user.has_perm("accounts.view_user"):
        main_items.append({
            "label": "User Management",
            "url": reverse("user-list"),
            "icon": "bi-people",
        })

    sections.append({
        "title": "MAIN MENU",
        "items": main_items,
    })

    # Business modules
    module_items = []

    # Employee requisition links
    if role == "employee":
        module_items.append({
            "label": "My Requisitions",
            "url": reverse("my-requisitions"),
            "icon": "bi-file-earmark-text",
            "disabled": False,
        })

    # New requisition
    module_items.append({
        "label": "New Requisition",
        "url": reverse("requisition-create"),
        "icon": "bi-plus-circle",
        "disabled": False,
    })

    # Reports - administrators only
    if role == "administrator":
        module_items.append({
            "label": "Reports",
            "url": reverse("report-index"),
            "icon": "bi-bar-chart-line",
            "disabled": False,
        })

    # My Items - employees can view their own assignments
    if (
        role == "employee"
        and user.has_perm("inventory.view_itemassignment")
    ):
        module_items.append({
            "label": "My Items",
            "url": reverse("inventory-my-items"),
            "icon": "bi-person-check",
            "disabled": False,
        })

    # Inventory navigation
    inventory_items = []

    if user.has_perm("inventory.view_inventoryitem"):
        inventory_items.append({
            "label": "Inventory Records",
            "url": reverse("inventory-item-list"),
            "icon": "bi-boxes",
            "disabled": False,
        })

    if user.has_perm("inventory.view_inventoryregistration"):
        inventory_items.append({
            "label": "Pending Registrations",
            "url": reverse("inventory-registration-queue"),
            "icon": "bi-clipboard-check",
            "disabled": False,
        })

        inventory_items.append({
            "label": "Registration History",
            "url": reverse("inventory-registration-history"),
            "icon": "bi-clock-history",
            "disabled": False,
        })

    if user.has_perm("inventory.view_itemcategory"):
        inventory_items.append({
            "label": "Item Categories",
            "url": reverse("inventory-category-list"),
            "icon": "bi-tags",
            "disabled": False,
        })

    # Assets
    if user.has_perm("inventory.view_asset"):
        inventory_items.append({
            "label": "Assets",
            "url": reverse("inventory-asset-list"),
            "icon": "bi-pc-display",
            "disabled": False,
        })

    # Full assignments list - inventory staff and administrators only
    if (
        role in ["inventory_staff", "administrator"]
        and user.has_perm("inventory.view_itemassignment")
    ):
        inventory_items.append({
            "label": "Assignments",
            "url": reverse("inventory-assignment-list"),
            "icon": "bi-person-lines-fill",
            "disabled": False,
        })

    # Fulfil requisitions
    if user.has_perm("inventory.issue_items"):
        inventory_items.append({
            "label": "Fulfil Requisitions",
            "url": reverse("inventory-fulfil-requisitions"),
            "icon": "bi-box-arrow-up",
            "disabled": False,
        })

    if inventory_items:
        module_items.append({
            "label": "Inventory",
            "url": None,
            "icon": "bi-box-seam",
            "disabled": True,
        })

        module_items.extend(inventory_items)

    # Procurement navigation
    procurement_items = []

    if user.has_perm("procurement.view_purchaserequest"):
        procurement_items.append({
            "label": "Purchase Requests",
            "url": reverse("procurement:purchase-request-list"),
            "icon": "bi-clipboard2-check",
            "disabled": False,
        })

    if user.has_perm("procurement.view_supplier"):
        procurement_items.append({
            "label": "Supplier Management",
            "url": reverse("procurement:supplier-list"),
            "icon": "bi-building",
            "disabled": False,
        })

    if user.has_perm("procurement.view_supplierquotation"):
        procurement_items.append({
            "label": "Supplier Quotations",
            "url": reverse("procurement:quotation-list"),
            "icon": "bi-file-earmark-text",
            "disabled": False,
        })

    if user.has_perm("procurement.view_purchaseorder"):
        procurement_items.append({
            "label": "Purchase Orders",
            "url": reverse("procurement:po-list"),
            "icon": "bi-receipt",
            "disabled": False,
        })

    # Budget Approvals - authorized Managers
    if (
        user.has_perm("procurement.view_budgetapproval")
        and user.has_perm("procurement.approve_budget")
    ):
        procurement_items.append({
            "label": "Budget Approvals",
            "url": reverse("procurement:budget-list"),
            "icon": "bi-clipboard-check",
            "disabled": False,
        })

    if procurement_items:
        module_items.append({
            "label": "Procurement",
            "url": None,
            "icon": "bi-cart",
            "disabled": True,
        })

        module_items.extend(procurement_items)

    # Receiving navigation
    if role == "receiving_staff":
        module_items.append({
            "label": "Expected Deliveries",
            "url": reverse("receiving:expected-deliveries"),
            "icon": "bi-truck",
            "disabled": False,
        })

        module_items.append({
            "label": "Discrepancy Management",
            "url": reverse("receiving:discrepancy-list"),
            "icon": "bi-exclamation-triangle",
            "disabled": False,
        })

    if module_items:
        sections.append({
            "title": "WORKSPACE",
            "items": module_items,
        })

    # User display information
    full_name = user.get_full_name().strip()
    display_name = full_name or user.username

    initials = "".join(
        part[0].upper()
        for part in display_name.split()
        if part
    )[:2]

    # Notifications
    notifications = []
    notification_count = 0

    # Purchasing staff: pending purchase requests
    if role == "purchasing_staff":
        pending_requests = PurchaseRequest.objects.filter(
            status=PurchaseRequest.Status.PENDING
        ).select_related(
            "requisition"
        ).order_by("-created_at")

        notification_count += pending_requests.count()

        for purchase_request in pending_requests[:5]:
            notifications.append({
                "title": (
                    f"New Purchase Request: "
                    f"{purchase_request.request_number}"
                ),
                "message": (
                    f"Requisition "
                    f"{purchase_request.requisition.requisition_number} "
                    f"has outstanding items to purchase."
                ),
            })

    # Employee: items awaiting acknowledgement
    if role == "employee":
        pending_assignments = ItemAssignment.objects.filter(
            assigned_to=user,
            status=ItemAssignment.Status.PENDING_ACKNOWLEDGEMENT,
        ).select_related(
            "requisition_item",
            "requisition_item__requisition",
            "inventory_item",
        ).order_by("-issued_at")

        notification_count += pending_assignments.count()

        for assignment in pending_assignments[:5]:
            notifications.append({
                "title": "Item Acknowledgement Required",
                "message": (
                    f"Please acknowledge receipt of "
                    f"{assignment.inventory_item.name} "
                    f"for requisition "
                    f"{assignment.requisition_item.requisition.requisition_number}."
                ),
            })

    # Inventory staff: requisitions ready for issuance
    if role == "inventory_staff":
        ready_requisitions = Requisition.objects.filter(
            status__in=[
                Requisition.Status.APPROVED,
                Requisition.Status.PARTIALLY_FULFILLED,
            ]
        ).order_by("-created_at")

        notification_count += ready_requisitions.count()

        for requisition in ready_requisitions[:5]:
            notifications.append({
                "title": "Requisition Ready for Issuance",
                "message": (
                    f"Requisition "
                    f"{requisition.requisition_number} "
                    f"has approved items awaiting fulfilment."
                ),
            })

    return {
        "nav_sections": sections,
        "ui_initials": initials or "U",
        "notification_count": notification_count,
        "notifications": notifications,
    }
