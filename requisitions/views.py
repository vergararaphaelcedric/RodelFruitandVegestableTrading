
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from accounts.models import User
from accounts.views import RoleRequiredMixin
from inventory.models import ItemAssignment

from .forms import (
    RequisitionDecisionForm,
    RequisitionForm,
    RequisitionItemFormSet,
    TrackingFilterForm,
)
from .models import Requisition
from .services import change_status, decide_requisition
from .tracking import build_tracker


class RequisitionCreateView(RoleRequiredMixin, View):
    required_role = User.Role.EMPLOYEE
    template_name = "requisitions/requisition_form.html"

    def get(self, request, *args, **kwargs):
        form = RequisitionForm()
        item_formset = RequisitionItemFormSet()

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "item_formset": item_formset,
                "page_title": "New Requisition",
            },
        )

    def post(self, request, *args, **kwargs):
        form = RequisitionForm(request.POST)
        item_formset = RequisitionItemFormSet(request.POST)

        if form.is_valid() and item_formset.is_valid():
            if not request.user.department:
                messages.error(
                    request,
                    "Your account has no department assigned. "
                    "Please contact the administrator.",
                )
                return redirect("dashboard-employee")

            try:
                with transaction.atomic():
                    requisition = form.save(commit=False)
                    requisition.requested_by = request.user
                    requisition.department = request.user.department
                    requisition.save()

                    item_formset.instance = requisition
                    item_formset.save()

                    change_status(
                        requisition=requisition,
                        new_status=Requisition.Status.SUBMITTED,
                        user=request.user,
                        remarks="Submitted by employee.",
                    )

            except Exception:
                messages.error(
                    request,
                    "Unable to submit your requisition. "
                    "Please check your information and try again.",
                )
                return render(
                    request,
                    self.template_name,
                    {
                        "form": form,
                        "item_formset": item_formset,
                        "page_title": "New Requisition",
                    },
                )

            messages.success(
                request,
                f"Requisition {requisition.requisition_number} "
                "submitted successfully!",
            )
            return redirect("dashboard-employee")

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "item_formset": item_formset,
                "page_title": "New Requisition",
            },
        )


class PendingRequisitionsView(RoleRequiredMixin, View):
    required_role = User.Role.MANAGER
    template_name = "requisitions/pending_list.html"

    def get(self, request, *args, **kwargs):
        requisitions = (
            Requisition.objects.filter(
                status=Requisition.Status.SUBMITTED
            )
            .select_related("requested_by", "department")
            .prefetch_related("items")
            .order_by("request_date", "id")
        )

        return render(
            request,
            self.template_name,
            {
                "requisitions": requisitions,
                "page_title": "Pending Requisitions",
            },
        )


class RequisitionReviewView(RoleRequiredMixin, View):
    required_role = User.Role.MANAGER
    template_name = "requisitions/requisition_review.html"

    def get_requisition(self, pk):
        return get_object_or_404(
            Requisition.objects.select_related(
                "requested_by", "department"
            ).prefetch_related("items", "items__inventory_item"),
            pk=pk,
        )

    def get(self, request, pk, *args, **kwargs):
        requisition = self.get_requisition(pk)
        form = RequisitionDecisionForm()

        return render(
            request,
            self.template_name,
            {
                "requisition": requisition,
                "form": form,
                "page_title": "Review Requisition",
            },
        )

    def post(self, request, pk, *args, **kwargs):
        requisition = self.get_requisition(pk)
        form = RequisitionDecisionForm(request.POST)

        if form.is_valid():
            try:
                decide_requisition(
                    requisition=requisition,
                    approver=request.user,
                    decision=form.cleaned_data["decision"],
                    remarks=form.cleaned_data["remarks"],
                )

            except (PermissionDenied, ValidationError) as error:
                messages.error(request, str(error))
                return redirect(
                    "requisition-review",
                    pk=requisition.pk,
                )

            decision = form.cleaned_data["decision"]

            messages.success(
                request,
                f"Requisition {requisition.requisition_number} "
                f"{decision} successfully.",
            )

            return redirect("pending-requisitions")

        return render(
            request,
            self.template_name,
            {
                "requisition": requisition,
                "form": form,
                "page_title": "Review Requisition",
            },
        )


class MyRequisitionsView(RoleRequiredMixin, View):
    required_role = User.Role.EMPLOYEE
    template_name = "requisitions/my_requisitions.html"

    def get(self, request, *args, **kwargs):
        form = TrackingFilterForm(request.GET or None)

        requisitions = (
            Requisition.objects.filter(requested_by=request.user)
            .select_related("department")
            .prefetch_related("items")
            .order_by("-request_date", "-id")
        )

        if form.is_valid():
            search = form.cleaned_data.get("search")
            status = form.cleaned_data.get("status")
            date_from = form.cleaned_data.get("date_from")
            date_to = form.cleaned_data.get("date_to")

            if search:
                requisitions = requisitions.filter(
                    requisition_number__icontains=search.strip()
                )

            if status:
                requisitions = requisitions.filter(status=status)

            if date_from:
                requisitions = requisitions.filter(
                    request_date__gte=date_from
                )

            if date_to:
                requisitions = requisitions.filter(
                    request_date__lte=date_to
                )

        paginator = Paginator(requisitions, 10)
        page_obj = paginator.get_page(request.GET.get("page"))

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_obj": page_obj,
                "requisitions": page_obj.object_list,
                "page_title": "My Requisitions",
            },
        )


class RequisitionDetailView(RoleRequiredMixin, View):
    required_role = User.Role.EMPLOYEE
    template_name = "requisitions/requisition_detail.html"

    def get(self, request, pk, *args, **kwargs):
        requisition = get_object_or_404(
            Requisition.objects.filter(
                requested_by=request.user
            )
            .select_related(
                "requested_by",
                "department",
            )
            .prefetch_related(
                "items",
                "items__inventory_item",
                "status_history",
                "approval_history",
                "approval_history__approver",
            ),
            pk=pk,
        )

        assignments = (
            ItemAssignment.objects.filter(
                requisition_item__requisition=requisition
            )
            .select_related(
                "requisition_item",
                "inventory_item",
                "assigned_to",
                "issued_by",
                "asset",
            )
            .order_by("issued_at", "id")
        )

        return render(
            request,
            self.template_name,
            {
                "requisition": requisition,
                "items": requisition.items.all(),
                "assignments": assignments,
                "status_history": requisition.status_history.all(),
                "approval_history": requisition.approval_history.all(),
                "page_title": "Requisition Details",
            },
        )


class RequisitionTrackingView(RoleRequiredMixin, View):
    required_role = User.Role.EMPLOYEE
    template_name = "requisitions/requisition_tracking.html"

    def get(self, request, pk, *args, **kwargs):
        requisition = get_object_or_404(
            Requisition.objects.filter(
                requested_by=request.user
            )
            .select_related("department")
            .prefetch_related(
                "status_history",
                "approval_history",
            ),
            pk=pk,
        )

        history = requisition.status_history.all()
        tracker_steps = build_tracker(requisition, history)

        return render(
            request,
            self.template_name,
            {
                "requisition": requisition,
                "tracker_steps": tracker_steps,
                "status_history": history,
                "page_title": "Track Requisition",
            },
        )
