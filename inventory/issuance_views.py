
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inventory.models import InventoryItem
from inventory.services import issue_requisition_item
from requisitions.models import Requisition, RequisitionItem


@login_required
@require_http_methods(["GET", "POST"])
def fulfil_requisitions(request):
    """Allow authorized inventory staff to issue approved requisition items."""

    if not request.user.has_perm("inventory.issue_items"):
        raise PermissionDenied(
            "You do not have permission to issue inventory items."
        )

    if request.method == "POST":
        requisition_item_id = request.POST.get("requisition_item_id")
        quantity = request.POST.get("quantity", "").strip()
        inventory_item_id = request.POST.get("inventory_item_id", "").strip()

        serial_numbers_text = request.POST.get(
            "serial_numbers",
            "",
        ).strip()

        serial_numbers = [
            value.strip()
            for value in serial_numbers_text.replace(",", "\n").splitlines()
            if value.strip()
        ]

        if not requisition_item_id:
            messages.error(request, "Please select a requisition item.")
            return redirect("inventory-fulfil-requisitions")

        try:
            requisition_item = get_object_or_404(
                RequisitionItem.objects.select_related("requisition"),
                pk=requisition_item_id,
            )

            issue_requisition_item(
                user=request.user,
                requisition_item_id=requisition_item.pk,
                quantity=quantity,
                inventory_item_id=inventory_item_id or None,
                serial_numbers=serial_numbers or None,
            )

        except (ValidationError, PermissionDenied, ValueError) as error:
            messages.error(request, str(error))
            return redirect("inventory-fulfil-requisitions")

        messages.success(
            request,
            (
                f"Issued {quantity} item(s) for "
                f"{requisition_item.requisition.requisition_number}."
            ),
        )

        return redirect("inventory-fulfil-requisitions")

    requisitions = (
        Requisition.objects.filter(
            status__in=[
                Requisition.Status.APPROVED,
                Requisition.Status.PARTIALLY_FULFILLED,
            ]
        )
        .select_related(
            "requested_by",
            "department",
        )
        .prefetch_related(
            "items",
            "items__inventory_item",
        )
        .order_by("request_date", "id")
    )

    inventory_items = InventoryItem.objects.all().order_by("name")

    context = {
        "requisitions": requisitions,
        "inventory_items": inventory_items,
    }

    return render(
        request,
        "inventory/fulfil_requisitions.html",
        context,
    )
