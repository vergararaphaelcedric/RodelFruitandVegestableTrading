
"""Single source of truth for roles and permissions."""

ROLE_GROUP_NAMES = {
    "administrator": "Administrator",
    "employee": "Employee",
    "manager": "Manager",
    "inventory_staff": "Inventory Staff",
    "purchasing_staff": "Purchasing Staff",
    "receiving_staff": "Receiving Staff",
}

DASHBOARD_URLS = {
    "administrator": "dashboard-administrator",
    "employee": "dashboard-employee",
    "manager": "dashboard-manager",
    "inventory_staff": "dashboard-inventory",
    "purchasing_staff": "dashboard-purchasing",
    "receiving_staff": "dashboard-receiving",
}

ROLE_SUMMARY = {
    "administrator": "Manage user accounts, roles and departments. Read-only access to inventory, requisitions, suppliers and quotations.",
    "employee": "Create requisitions and track your own requests. View inventory items.",
    "manager": "Review and approve or reject submitted requisitions. View inventory.",
    "inventory_staff": "Maintain inventory items and categories, and record fulfilment of requisition lines.",
    "purchasing_staff": "View requisitions and stock levels, manage Purchase Requests, suppliers and supplier quotations, and plan purchases.",
    "receiving_staff": "Verify issued purchase orders, record deliveries, report discrepancies, and track supplier resolutions.",
}


def perms(app, model, *actions):
    return [f"{app}.{action}_{model}" for action in actions]


ROLE_PERMISSIONS = {
    "administrator": [
        *perms("accounts", "user", "add", "change", "view"),
        *perms("accounts", "department", "add", "change", "view"),
        *perms("inventory", "inventoryitem", "view"),
        *perms("inventory", "itemcategory", "view"),
        *perms("inventory", "inventorytransaction", "view"),
        *perms("requisitions", "requisition", "view"),
        *perms("requisitions", "requisitionitem", "view"),
        *perms("requisitions", "statushistory", "view"),
        *perms("requisitions", "approvalhistory", "view"),
        *perms("requisitions", "stockreservation", "view"),
        *perms("procurement", "purchaserequest", "view"),
        *perms("procurement", "purchaserequestitem", "view"),
        *perms("procurement", "supplier", "view"),
        *perms("procurement", "supplierquotation", "view"),
        *perms("procurement", "budgetapproval", "view"),
        *perms("procurement", "purchaseorder", "view"),
        *perms("procurement", "purchaseorderitem", "view"),
    ],
    "employee": [
        *perms("requisitions", "requisition", "add", "change", "view"),
        *perms("requisitions", "requisitionitem", "add", "change", "view"),
        *perms("inventory", "inventoryitem", "view"),
        *perms("inventory", "itemcategory", "view"),
    ],
    "manager": [
        *perms("requisitions", "requisition", "view"),
        "requisitions.approve_requisition",
        *perms("requisitions", "requisitionitem", "view"),
        *perms("requisitions", "statushistory", "view"),
        *perms("requisitions", "approvalhistory", "view"),
        *perms("inventory", "inventoryitem", "view"),
        *perms("inventory", "itemcategory", "view"),
        *perms("procurement", "budgetapproval", "view"),
        "procurement.approve_budget",
    ],
    "inventory_staff": [
        *perms("inventory", "inventoryitem", "add", "change", "view"),
        *perms("inventory", "itemcategory", "add", "change", "view"),
        *perms("inventory", "inventorytransaction", "view"),
        *perms("inventory", "inventoryregistration", "add", "view"),
        *perms("requisitions", "requisition", "view"),
        *perms("requisitions", "requisitionitem", "change", "view"),
        *perms("requisitions", "stockreservation", "view"),
    ],
    "purchasing_staff": [
        *perms("inventory", "inventoryitem", "view"),
        *perms("inventory", "itemcategory", "view"),
        *perms("inventory", "inventorytransaction", "view"),
        *perms("requisitions", "requisition", "view"),
        *perms("requisitions", "requisitionitem", "view"),
        *perms("requisitions", "stockreservation", "view"),
        *perms("procurement", "purchaserequest", "view", "change"),
        *perms("procurement", "purchaserequestitem", "view"),
        *perms("procurement", "supplier", "add", "change", "delete", "view"),
        *perms("procurement", "supplierquotation", "add", "change", "delete", "view"),
        *perms("procurement", "budgetapproval", "view"),
        *perms("procurement", "purchaseorder", "add", "change", "view"),
        *perms("procurement", "purchaseorderitem", "view"),
    ],
    "receiving_staff": [
    # Inventory reference access
        *perms("inventory", "inventoryitem", "view"),
        *perms("inventory", "itemcategory", "view"),

    # Delivery receiving
        *perms("receiving", "deliveryreceipt", "add", "view"),
        *perms("receiving", "deliveryreceiptitem", "add", "view"),

    # Discrepancy reporting and supplier resolution
        *perms("receiving", "deliverydiscrepancy", "add", "change", "view"),
    ],
}
