
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from requisitions.forms import ApprovalDecisionForm

from .forms import BudgetFilterForm
from .models import BudgetApproval
from .purchasing import can_review_budget, decide_budget
from .views import FilteredListMixin


class BudgetApproverMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Anonymous -> login. Not a Manager with approve_budget -> 403."""

    def test_func(self):
        return can_review_budget(self.request.user)


class BudgetListView(BudgetApproverMixin, FilteredListMixin, ListView):
    template_name = "procurement/budget_list.html"
    context_object_name = "approvals"
    filter_form_class = BudgetFilterForm

    def get_queryset(self):
        qs = (
            BudgetApproval.objects.select_related(
                "purchase_request__requisition",
                "requested_by",
                "decided_by",
            )
            .annotate(
                order=Case(
                    When(status="pending", then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .exclude(requested_by=self.request.user)
            .order_by("order", "-requested_at")
        )

        filters = self.get_filters()

        if filters.get("q"):
            qs = qs.filter(
                Q(
                    purchase_request__request_number__icontains=filters["q"]
                )
                | Q(
                    purchase_request__requisition__requisition_number__icontains=filters["q"]
                )
            )

        if filters.get("status"):
            qs = qs.filter(status=filters["status"])

        return qs


class BudgetReviewView(BudgetApproverMixin, View):
    template_name = "procurement/budget_review.html"

    def get_approval(self, pk):
        return get_object_or_404(
            BudgetApproval.objects.select_related(
                "purchase_request__requisition__requested_by",
                "purchase_request__requisition__department",
                "requested_by",
                "decided_by",
            ).exclude(requested_by=self.request.user),
            pk=pk,
        )

    def render_page(self, request, approval, form):
        return render(
            request,
            self.template_name,
            {
                "approval": approval,
                "purchase": approval.purchase_request,
                "form": form,
                "lines": approval.snapshot,
                "title": (
                    f"Budget review "
                    f"{approval.purchase_request.request_number}"
                ),
            },
        )

    def get(self, request, pk):
        return self.render_page(
            request,
            self.get_approval(pk),
            ApprovalDecisionForm(),
        )

    def post(self, request, pk):
        approval = self.get_approval(pk)
        form = ApprovalDecisionForm(request.POST)

        if not form.is_valid():
            return self.render_page(request, approval, form)

        decision = form.cleaned_data["decision"]
        number = approval.purchase_request.request_number

        try:
            decide_budget(
                approval,
                request.user,
                decision,
                form.cleaned_data["remarks"],
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("budget-review", pk=approval.pk)

        if decision == "approved":
            messages.success(
                request,
                f"Budget for {number} was approved. "
                "Purchasing can now generate purchase orders.",
            )
        else:
            messages.success(
                request,
                f"Budget for {number} was rejected and returned to Purchasing.",
            )

        return redirect("procurement:budget-list")
