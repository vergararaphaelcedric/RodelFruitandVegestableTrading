
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .models import SupplierQuotation


CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def build_comparison(purchase_request, today=None):
    today = today or timezone.localdate()

    items = list(
        purchase_request.items
        .select_related("inventory_item")
        .order_by("pk")
    )

    quotes = (
        SupplierQuotation.objects
        .filter(
            purchase_request_item__purchase_request=purchase_request
        )
        .select_related("supplier")
        .order_by("-quotation_date", "-id")
    )

    # Only the newest quotation per supplier per item counts.
    latest = {}
    older = 0

    for quote in quotes:
        key = (
            quote.purchase_request_item_id,
            quote.supplier_id,
        )

        if key in latest:
            older += 1
        else:
            latest[key] = quote

    by_item = defaultdict(list)

    for quote in latest.values():
        by_item[quote.purchase_request_item_id].append(quote)

    lines = []
    eligible_by_supplier = defaultdict(dict)

    for item in items:
        required = item.quantity_shortage
        rows = []

        for quote in by_item.get(item.pk, []):
            expired = quote.valid_until < today
            inactive = not quote.supplier.is_active

            rows.append({
                "quote": quote,
                "cost": money(quote.unit_price * required),
                "expired": expired,
                "inactive": inactive,
                "qty_differs": quote.quantity != required,
                "eligible": not expired and not inactive,
                "best": False,
                "diff_amount": None,
                "diff_pct": None,
            })

        rows.sort(
            key=lambda row: (
                not row["eligible"],
                row["quote"].unit_price,
                row["quote"].supplier.name.lower(),
            )
        )

        eligible = [
            row for row in rows
            if row["eligible"]
        ]

        best = eligible[0] if eligible else None

        for row in eligible:
            row["best"] = (
                row["quote"].unit_price
                == best["quote"].unit_price
            )

            row["diff_amount"] = (
                row["cost"] - best["cost"]
            )

            row["diff_pct"] = (
                (
                    row["quote"].unit_price
                    / best["quote"].unit_price - 1
                ) * 100
            ).quantize(Decimal("0.1"))

            eligible_by_supplier[
                row["quote"].supplier_id
            ][item.pk] = row

        lines.append({
            "item": item,
            "rows": rows,
            "best": best,
            "eligible_count": len(eligible),
        })

    # Suppliers with valid quotations for every item.
    suppliers = []

    for rows_by_item in eligible_by_supplier.values():
        if items and len(rows_by_item) == len(items):
            total = sum(
                (
                    row["cost"]
                    for row in rows_by_item.values()
                ),
                Decimal("0"),
            )

            supplier = next(
                iter(rows_by_item.values())
            )["quote"].supplier

            suppliers.append({
                "supplier": supplier,
                "total": money(total),
                "cheapest": False,
            })

    suppliers.sort(
        key=lambda entry: (
            entry["total"],
            entry["supplier"].name.lower(),
        )
    )

    if suppliers:
        suppliers[0]["cheapest"] = True

    all_quoted = (
        bool(items)
        and all(line["best"] for line in lines)
    )

    combined = (
        money(
            sum(
                (line["best"]["cost"] for line in lines),
                Decimal("0"),
            )
        )
        if all_quoted
        else None
    )

    single_best = (
        suppliers[0]["total"]
        if suppliers
        else None
    )

    savings = (
        money(single_best - combined)
        if combined is not None and single_best is not None
        else None
    )

    return {
        "lines": lines,
        "suppliers": suppliers,
        "all_quoted": all_quoted,
        "combined_total": combined,
        "single_best": single_best,
        "savings": savings,
        "quote_count": len(latest),
        "older_count": older,

        # Compatibility with the existing review view.
        "has_items": bool(items),
        "all_have_quotes": all_quoted,
    }
