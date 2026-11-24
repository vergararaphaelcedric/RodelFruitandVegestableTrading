from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .comparison import build_comparison
from .models import (
    BudgetApproval,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    SupplierQuotation,
)

PR = PurchaseRequest.Status
BA = BudgetApproval.Status
ZERO = Decimal("0")


def can_review_budget(user):
    """Only active users with the Manager role and the approve_budget permission."""
    return bool(
        user.is_active
        and user.role == "manager"
        and user.has_perm("procurement.approve_budget")
    )

def submit_for_budget_approval(purchase_request, selections, user, notes=""):
    """Submit selected quotations for manager budget approval."""
    if not (user.is_active and user.has_perm("procurement.change_purchaserequest")):
        raise PermissionDenied("You do not have permission to submit purchase requests for approval.")

    with transaction.atomic():
        pr = PurchaseRequest.objects.select_for_update().get(pk=purchase_request.pk)

        if pr.status != PR.PENDING:
            raise ValidationError("Only pending purchase requests can be submitted for budget approval.")

        comparison = build_comparison(pr)

        if not comparison["lines"]:
            raise ValidationError("This purchase request has no items.")

        chosen, snapshot, total = [], [], ZERO

        for line in comparison["lines"]:
            item = line["item"]

            row = next(
                (r for r in line["rows"] if r["quote"].pk == selections.get(item.pk)),
                None,
            )

            if row is None:
                raise ValidationError(f"Select a current quotation for {item.item_description}.")

            if not row["eligible"]:
                raise ValidationError(
                    f"The quotation from {row['quote'].supplier.name} for "
                    f"{item.item_description} is expired or from an inactive supplier."
                )

            quote = row["quote"]
            line_total = SupplierQuotation.compute_total(
                item.quantity_shortage, quote.unit_price
            )
            lowest = line["best"]["quote"].unit_price

            chosen.append((item, quote))
            total += line_total

            snapshot.append({
                "item": item.item_description,
                "unit": item.get_unit_of_measure_display().lower(),
                "quantity": str(item.quantity_shortage),
                "supplier": quote.supplier.name,
                "supplier_id": quote.supplier_id,
                "quotation": quote.quotation_number,
                "unit_price": str(quote.unit_price),
                "line_total": str(line_total),
                "lowest_unit_price": str(lowest),
                "is_lowest": quote.unit_price <= lowest,
            })

        approval = BudgetApproval.objects.create(
            purchase_request=pr,
            requested_by=user,
            request_notes=(notes or "").strip(),
            total_amount=total,
            snapshot=snapshot,
        )

        for item, quote in chosen:
            item.selected_quotation = quote
            item.save(update_fields=["selected_quotation"])

        pr.status = PR.BUDGET_REVIEW
        pr.save(update_fields=["status", "updated_at"])

    return approval


def decide_budget(approval, approver, decision, remarks=""):
    remarks = (remarks or "").strip()

    if decision not in (BA.APPROVED, BA.REJECTED):
        raise ValidationError("Decision must be 'approved' or 'rejected'.")

    if not can_review_budget(approver):
        raise PermissionDenied("You do not have permission to approve or reject budgets.")

    today = timezone.localdate()

    with transaction.atomic():
        ba = BudgetApproval.objects.select_for_update().get(pk=approval.pk)

        if approver.pk == ba.requested_by_id:
            raise PermissionDenied("You cannot decide a budget you requested yourself.")

        if ba.status != BA.PENDING:
            raise ValidationError("This budget request has already been decided.")

        pr = PurchaseRequest.objects.select_for_update().get(
            pk=ba.purchase_request_id
        )

        if pr.status != PR.BUDGET_REVIEW:
            raise ValidationError(
                "The purchase request is no longer awaiting budget approval."
            )

        if decision == BA.REJECTED and not remarks:
            raise ValidationError("Remarks are required when rejecting a budget.")

        items = list(
            pr.items.select_related("selected_quotation").order_by("pk")
        )

        if decision == BA.APPROVED:
            if any(i.selected_quotation_id is None for i in items):
                raise ValidationError("Not every item has a selected quotation.")

            if any(i.selected_quotation.valid_until < today for i in items):
                raise ValidationError(
                    "A selected quotation has expired. Reject this request so "
                    "Purchasing can obtain a new quotation."
                )

            recomputed = sum(
                (
                    SupplierQuotation.compute_total(
                        i.quantity_shortage,
                        i.selected_quotation.unit_price,
                    )
                    for i in items
                ),
                ZERO,
            )

            if recomputed != ba.total_amount:
                raise ValidationError(
                    "The selected quotations no longer match the requested budget."
                )

        ba.status = decision
        ba.decided_by = approver
        ba.decided_at = timezone.now()
        ba.remarks = remarks
        ba.save()

        if decision == BA.APPROVED:
            pr.status = PR.BUDGET_APPROVED
        else:
            pr.items.update(selected_quotation=None)
            pr.status = PR.PENDING

        pr.save(update_fields=["status", "updated_at"])

    approval.status = ba.status
    return ba


def generate_purchase_orders(purchase_request, user):
    """Create one draft purchase order per selected supplier."""
    if not (user.is_active and user.has_perm("procurement.add_purchaseorder")):
        raise PermissionDenied("You do not have permission to generate purchase orders.")

    with transaction.atomic():
        pr = PurchaseRequest.objects.select_for_update().get(
            pk=purchase_request.pk
        )

        if pr.status != PR.BUDGET_APPROVED:
            raise ValidationError(
                "Purchase orders can only be generated after the budget is approved."
            )

        approval = (
            BudgetApproval.objects.select_for_update()
            .filter(purchase_request=pr, status=BA.APPROVED)
            .first()
        )

        if approval is None:
            raise ValidationError("No approved budget was found for this purchase request.")

        items = list(
            pr.items.select_related("selected_quotation__supplier").order_by("pk")
        )

        if any(i.selected_quotation_id is None for i in items):
            raise ValidationError("Not every item has a selected quotation.")

        if pr.purchase_orders.exists():
            raise ValidationError("Purchase orders were already generated for this request.")

        groups = {}

        for item in items:
            groups.setdefault(
                item.selected_quotation.supplier_id, []
            ).append(item)

        priced = {
            i.pk: SupplierQuotation.compute_total(
                i.quantity_shortage,
                i.selected_quotation.unit_price,
            )
            for i in items
        }

        if sum(priced.values(), ZERO) != approval.total_amount:
            raise ValidationError(
                "The selected quotations no longer match the approved budget."
            )

        orders = []

        for group in sorted(
            groups.values(),
            key=lambda g: g[0].selected_quotation.supplier.name.lower(),
        ):
            supplier = group[0].selected_quotation.supplier

            po = PurchaseOrder.objects.create(
                purchase_request=pr,
                budget_approval=approval,
                supplier=supplier,
                supplier_name=supplier.name,
                supplier_address=supplier.address,
                supplier_contact=supplier.contact_person,
                supplier_email=supplier.email,
                supplier_phone=supplier.phone,
                payment_terms=supplier.payment_terms,
                created_by=user,
            )

            amount = ZERO

            for item in group:
                quote = item.selected_quotation

                PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    purchase_request_item=item,
                    quotation=quote,
                    inventory_item=item.inventory_item,
                    item_description=item.item_description,
                    unit_of_measure=item.unit_of_measure,
                    quantity=item.quantity_shortage,
                    unit_price=quote.unit_price,
                    line_total=priced[item.pk],
                )

                amount += priced[item.pk]

            po.total_amount = amount
            po.save(update_fields=["total_amount", "updated_at"])

            orders.append(po)

    return orders


def issue_purchase_order(purchase_order, user):
    """Issue a draft purchase order after rechecking its approved budget."""
    if not (user.is_active and user.has_perm("procurement.change_purchaseorder")):
        raise PermissionDenied("You do not have permission to issue purchase orders.")

    with transaction.atomic():
        po = (
            PurchaseOrder.objects.select_for_update()
            .select_related("budget_approval")
            .get(pk=purchase_order.pk)
        )

        if po.status != PurchaseOrder.Status.DRAFT:
            raise ValidationError("Only draft purchase orders can be issued.")

        if po.budget_approval.status != BA.APPROVED:
            raise PermissionDenied(
                "A purchase order cannot be issued before its budget is approved."
            )

        po.status = PurchaseOrder.Status.ISSUED
        po.issued_at = timezone.now()
        po.issued_by = user

        po.save(
            update_fields=["status", "issued_at", "issued_by", "updated_at"]
        )

        pr = PurchaseRequest.objects.select_for_update().get(
            pk=po.purchase_request_id
        )

        all_issued = not pr.purchase_orders.exclude(
            status=PurchaseOrder.Status.ISSUED
        ).exists()

        if all_issued and pr.status == PR.BUDGET_APPROVED:
            pr.status = PR.ORDERED
            pr.save(update_fields=["status", "updated_at"])

    purchase_order.refresh_from_db()
    return po