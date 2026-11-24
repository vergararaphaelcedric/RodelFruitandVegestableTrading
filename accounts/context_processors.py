
from django.urls import reverse

from procurement.models import PurchaseRequest


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

    if role == "employee":
        module_items.append({
            "label": "My Requisitions",
            "url": reverse("my-requisitions"),
            "icon": "bi-file-earmark-text",
            "disabled": False,
        })

    module_items.append({
        "label": "New Requisition",
        "url": reverse("requisition-create"),
        "icon": "bi-plus-circle",
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

    if role == "purchasing_staff":
        pending_requests = PurchaseRequest.objects.filter(
            status=PurchaseRequest.Status.PENDING
        ).select_related(
            "requisition"
        ).order_by("-created_at")

        notification_count = pending_requests.count()

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

    return {
        "nav_sections": sections,
        "ui_initials": initials or "U",
        "notification_count": notification_count,
        "notifications": notifications,
    }
