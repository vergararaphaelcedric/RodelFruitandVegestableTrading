
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from accounts.models import User
from procurement.models import PurchaseRequest

from .forms import ApprovalDecisionForm, ManagerFilterForm
from .models import ApprovalHistory, Requisition, RequisitionItem, StatusHistory
from .queries import pending_for, reviewable_requisitions, with_list_annotations
from .services import decide_requisition
from .stock import describe, stock_check


S = Requisition.Status

APPROVED_STATUSES = [
    S.APPROVED,
    S.PARTIALLY_FULFILLED,
    S.FULFILLED,
]


class ManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only active users with the Manager role and approval permission."""

    def test_func(self):
        user = self.request.user

        return (
            user.is_authenticated
            and user.is_active
            and user.role == User.Role.MANAGER
            and user.has_perm("requisitions.approve_requisition")
        )


class ManagerListMixin(ManagerRequiredMixin):
    paginate_by = 10
    title = ""
    subtitle = ""
    empty_message = "Nothing to show."
    mode = "decided"
    status_choices = None
    status_label = "Status"
    allow_mine = False

    def get_filter_form(self):
        if not hasattr(self, "_filter_form"):
            self._filter_form = ManagerFilterForm(
                self.request.GET or None,
                status_choices=self.status_choices,
                status_label=self.status_label,
                allow_mine=self.allow_mine,
            )

        return self._filter_form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        params = self.request.GET.copy()
        params.pop("page", None)

        context.update({
            "page_title": self.title,
            "page_description": self.subtitle,
            "empty_message": self.empty_message,
            "mode": self.mode,
            "filter_form": self.get_filter_form(),
            "querystring": params.urlencode(),
            "filters_active": any(params.values()),
        })

        return context


class PendingApprovalListView(ManagerListMixin, ListView):
    template_name = "approvals/requisition_list.html"
    context_object_name = "requisitions"

    title = "Pending Requisitions"
    subtitle = "Submitted requests waiting for your decision."
    empty_message = "Nothing is waiting for your approval."
    mode = "pending"

    def get_queryset(self):
        queryset = with_list_annotations(
            pending_for(self.request.user)
        ).order_by("request_date", "id")

        return self.get_filter_form().filter_queryset(queryset)


class DecidedRequisitionListView(ManagerListMixin, ListView):
    template_name = "approvals/requisition_list.html"
    context_object_name = "requisitions"

    statuses = ()

    def get_queryset(self):
        queryset = (
            with_list_annotations(
                reviewable_requisitions(self.request.user).filter(
                    status__in=self.statuses
                )
            )
            .prefetch_related(
                Prefetch(
                    "approval_history",
                    queryset=ApprovalHistory.objects.select_related(
                        "approver"
                    ),
                )
            )
            .order_by("-decided_at", "-id")
        )

        return self.get_filter_form().filter_queryset(queryset)


class ApprovedRequisitionListView(DecidedRequisitionListView):
    title = "Approved Requisitions"
    subtitle = "Approved requests, including those being fulfilled."
    empty_message = "No approved requisitions yet."

    statuses = APPROVED_STATUSES

    status_choices = [
        (S.APPROVED, "Approved"),
        (S.PARTIALLY_FULFILLED, "Partially Fulfilled"),
        (S.FULFILLED, "Fulfilled"),
    ]


class RejectedRequisitionListView(DecidedRequisitionListView):
    title = "Rejected Requisitions"
    subtitle = "Requests that managers rejected, including their remarks."
    empty_message = "No rejected requisitions yet."

    statuses = [S.REJECTED]

    status_choices = [
        (S.REJECTED, "Rejected"),
    ]


class ManagerApprovalHistoryView(ManagerListMixin, ListView):
    template_name = "approvals/approval_history.html"
    context_object_name = "records"

    paginate_by = 15

    title = "Approval History"
    subtitle = "Recorded approval and rejection decisions."
    empty_message = "No approval decisions recorded yet."

    status_choices = ApprovalHistory.Decision.choices
    status_label = "Decision"
    allow_mine = True

    def get_queryset(self):
        queryset = ApprovalHistory.objects.select_related(
            "requisition",
            "requisition__requested_by",
            "requisition__department",
            "approver",
        ).order_by("-acted_at", "-id")

        form = self.get_filter_form()

        queryset = form.filter_queryset(
            queryset,
            number="requisition__requisition_number",
            status="decision",
            date="acted_at__date",
        )

        if (
            form.is_bound
            and form.is_valid()
            and form.cleaned_data.get("mine")
        ):
            queryset = queryset.filter(
                approver=self.request.user
            )

        return queryset


class ManagerRequisitionReviewView(ManagerRequiredMixin, View):
    template_name = "approvals/review.html"

    def get_requisition(self, pk):
        queryset = reviewable_requisitions(
            self.request.user
        ).prefetch_related(
            Prefetch(
                "items",
                queryset=RequisitionItem.objects.select_related(
                    "inventory_item"
                ),
            ),
            Prefetch(
                "status_history",
                queryset=StatusHistory.objects.select_related(
                    "changed_by"
                ),
            ),
            Prefetch(
                "approval_history",
                queryset=ApprovalHistory.objects.select_related(
                    "approver"
                ),
            ),
        )

        return get_object_or_404(queryset, pk=pk)

    def render_page(self, request, requisition, form):
        stock_data = stock_check(requisition)

        rows = []

        for stock_row in stock_data["rows"]:
            rows.append({
                "line": stock_row["line"],
                "stock": stock_row["available"],
                "reserved": stock_row["reserved"],
                "shortage": stock_row["shortage"],
                "short": stock_row["shortage"] > 0,
                "outcome": stock_row["outcome"],
                "stock_requested": stock_row["requested"],
            })

        return render(
            request,
            self.template_name,
            {
                "requisition": requisition,
                "rows": rows,
                "stock_data": stock_data,
                "history": list(requisition.status_history.all()),
                "approvals": list(requisition.approval_history.all()),
                "form": form,
                "page_title": (
                    f"Review {requisition.requisition_number}"
                ),
            },
        )

    def get(self, request, pk):
        requisition = self.get_requisition(pk)

        return self.render_page(
            request,
            requisition,
            ApprovalDecisionForm(),
        )

    def post(self, request, pk):
        requisition = self.get_requisition(pk)
        form = ApprovalDecisionForm(request.POST)

        if not form.is_valid():
            return self.render_page(
                request,
                requisition,
                form,
            )

        decision = form.cleaned_data["decision"]
        remarks = form.cleaned_data["remarks"]

        try:
            decide_requisition(
                requisition=requisition,
                approver=request.user,
                decision=decision,
                remarks=remarks,
            )

        except ValidationError as error:
            messages.error(
                request,
                "; ".join(error.messages),
            )

            return redirect(
                "manager-review",
                pk=requisition.pk,
            )

        if decision == ApprovalHistory.Decision.APPROVED:
            requisition.refresh_from_db()

            stock_data = stock_check(requisition)

            messages.success(
                request,
                describe(stock_data),
            )

            purchase_request = PurchaseRequest.objects.filter(
                requisition=requisition
            ).first()

            if purchase_request:
                messages.warning(
                    request,
                    (
                        f"Purchase Request {purchase_request.request_number} "
                        "was automatically created for outstanding items."
                    ),
                )

        else:
            messages.success(
                request,
                (
                    f"{requisition.requisition_number} "
                    "was rejected successfully."
                ),
            )

        return redirect("manager-pending")
