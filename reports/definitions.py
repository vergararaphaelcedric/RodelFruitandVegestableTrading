
from dataclasses import dataclass

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q


@dataclass(frozen=True)
class Column:
    label: str
    accessor: str


class ReportDefinition:
    def __init__(
        self,
        slug,
        title,
        description,
        model_label,
        columns,
        ordering=None,
    ):
        self.slug = slug
        self.title = title
        self.description = description
        self.model_label = model_label
        self.columns = columns
        self.ordering = ordering or []

    def get_model(self):
        try:
            app_label, model_name = self.model_label.split(".", 1)
            return apps.get_model(app_label, model_name)
        except (LookupError, ValueError):
            return None

    def get_queryset(self, request=None):
        model = self.get_model()

        if model is None:
            return []

        queryset = model.objects.all()

        if self.ordering:
            queryset = queryset.order_by(*self.ordering)

        search_term = ""

        if request is not None:
            search_term = request.GET.get("search", "").strip()

        if not search_term:
            return queryset

        search_fields = set()

        text_field_types = {
            "CharField",
            "TextField",
            "EmailField",
            "SlugField",
        }

        def add_text_fields_from_model(current_model, prefix=""):
            """
            Add searchable text fields from a model.

            If prefix is supplied, search through a related object,
            for example requester__username.
            """
            for field in current_model._meta.get_fields():
                if not getattr(field, "concrete", False):
                    continue

                if getattr(field, "is_relation", False):
                    continue

                field_type = field.get_internal_type()

                if field_type not in text_field_types:
                    continue

                if prefix:
                    field_path = f"{prefix}__{field.name}"
                else:
                    field_path = field.name

                search_fields.add(field_path)

        # Search text fields directly on the report model.
        add_text_fields_from_model(model)

        # Search text fields on related objects used by report columns.
        for column in self.columns:
            current_model = model
            prefix = ""

            for part in column.accessor.split("__"):
                try:
                    field = current_model._meta.get_field(part)
                except FieldDoesNotExist:
                    break

                if prefix:
                    prefix = f"{prefix}__{part}"
                else:
                    prefix = part

                if field.is_relation and field.related_model:
                    current_model = field.related_model

                    add_text_fields_from_model(
                        current_model,
                        prefix,
                    )
                else:
                    break

        if search_fields:
            search_query = Q()

            for field_name in search_fields:
                search_query |= Q(
                    **{
                        f"{field_name}__icontains": search_term
                    }
                )

            queryset = queryset.filter(search_query).distinct()

        return queryset

    def __str__(self):
        return self.title


def model_exists(model_label):
    try:
        app_label, model_name = model_label.split(".", 1)
        return apps.get_model(app_label, model_name) is not None
    except (LookupError, ValueError):
        return False


def get_first_existing_model(*model_labels):
    for model_label in model_labels:
        if model_exists(model_label):
            return model_label

    return model_labels[0]


def get_first_existing_field(model_label, *field_names):
    try:
        app_label, model_name = model_label.split(".", 1)
        model = apps.get_model(app_label, model_name)
    except (LookupError, ValueError):
        return "id"

    for field_name in field_names:
        try:
            model._meta.get_field(field_name)
            return field_name
        except FieldDoesNotExist:
            continue

    return "id"


def make_report(
    slug,
    title,
    description,
    model_label,
    field_options,
    ordering=None,
):
    columns = []

    for label, candidates in field_options:
        accessor = get_first_existing_field(
            model_label,
            *candidates,
        )

        columns.append(
            Column(
                label=label,
                accessor=accessor,
            )
        )

    return ReportDefinition(
        slug=slug,
        title=title,
        description=description,
        model_label=model_label,
        columns=columns,
        ordering=ordering,
    )


REQUISITION_MODEL = get_first_existing_model(
    "requisitions.Requisition",
)

PURCHASE_MODEL = get_first_existing_model(
    "procurement.PurchaseOrder",
)

INVENTORY_MODEL = get_first_existing_model(
    "inventory.InventoryItem",
)

ASSET_MODEL = get_first_existing_model(
    "inventory.Asset",
)

DELIVERY_MODEL = get_first_existing_model(
    "receiving.DeliveryReceipt",
)


REPORTS = {
    "requisitions": make_report(
        slug="requisitions",
        title="Requisition Report",
        description="View internal requisition records and their statuses.",
        model_label=REQUISITION_MODEL,
        field_options=[
            (
                "Requisition Number",
                (
                    "reference_number",
                    "requisition_number",
                    "request_number",
                    "id",
                ),
            ),
            (
                "Requester",
                (
                    "requester",
                    "created_by",
                    "employee",
                ),
            ),
            (
                "Department",
                (
                    "department",
                ),
            ),
            (
                "Status",
                (
                    "status",
                ),
            ),
            (
                "Date Submitted",
                (
                    "submitted_at",
                    "created_at",
                    "date_created",
                ),
            ),
        ],
        ordering=["-id"],
    ),

    "purchasing": make_report(
        slug="purchasing",
        title="Purchasing Report",
        description="Review purchase orders and purchasing activity.",
        model_label=PURCHASE_MODEL,
        field_options=[
            (
                "Purchase Order",
                (
                    "po_number",
                    "purchase_order_number",
                    "number",
                    "id",
                ),
            ),
            (
                "Supplier",
                (
                    "supplier",
                ),
            ),
            (
                "Status",
                (
                    "status",
                ),
            ),
            (
                "Date Created",
                (
                    "created_at",
                    "issued_at",
                    "date_created",
                ),
            ),
        ],
        ordering=["-id"],
    ),

    "inventory": make_report(
        slug="inventory",
        title="Inventory Report",
        description="Review current inventory items and stock quantities.",
        model_label=INVENTORY_MODEL,
        field_options=[
            (
                "Item Name",
                (
                    "name",
                    "item_name",
                    "description",
                ),
            ),
            (
                "Item Code",
                (
                    "item_code",
                    "sku",
                    "code",
                ),
            ),
            (
                "Category",
                (
                    "category",
                ),
            ),
            (
                "Quantity on Hand",
                (
                    "quantity_on_hand",
                    "quantity",
                    "stock_quantity",
                ),
            ),
            (
                "Quantity Reserved",
                (
                    "quantity_reserved",
                    "reserved_quantity",
                ),
            ),
        ],
        ordering=["id"],
    ),

    "assets": make_report(
        slug="assets",
        title="Asset Report",
        description="Review tracked assets and their current status.",
        model_label=ASSET_MODEL,
        field_options=[
            (
                "Asset Tag",
                (
                    "asset_tag",
                    "tag_number",
                    "id",
                ),
            ),
            (
                "Inventory Item",
                (
                    "inventory_item",
                ),
            ),
            (
                "Status",
                (
                    "status",
                ),
            ),
            (
                "Date Created",
                (
                    "created_at",
                    "date_created",
                ),
            ),
        ],
        ordering=["-id"],
    ),

    "deliveries": make_report(
        slug="deliveries",
        title="Delivery Report",
        description="Review delivery receipts and receiving activity.",
        model_label=DELIVERY_MODEL,
        field_options=[
            (
                "Delivery Receipt",
                (
                    "receipt_number",
                    "dr_number",
                    "reference_number",
                    "id",
                ),
            ),
            (
                "Purchase Order",
                (
                    "purchase_order",
                ),
            ),
            (
                "Status",
                (
                    "status",
                ),
            ),
            (
                "Date Received",
                (
                    "received_at",
                    "receipt_date",
                    "created_at",
                ),
            ),
        ],
        ordering=["-id"],
    ),
}
