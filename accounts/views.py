
from django.contrib import messages
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UserPassesTestMixin,
)
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from inventory.models import InventoryItem
from procurement.models import PurchaseRequest, PurchaseRequestItem
from requisitions.models import Requisition

from .forms import UserCreateForm, UserUpdateForm
from .models import Department, User
from .roles import ROLE_SUMMARY


def manageable_users(user):
    """Return accounts the current user is allowed to manage."""

    queryset = User.objects.select_related(
        "department"
    ).order_by("username")

    # Non-superusers must never manage superuser accounts.
    if not user.is_superuser:
        queryset = queryset.filter(is_superuser=False)

    return queryset


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict a page to users with a specific role."""

    required_role = None

    def test_func(self):
        user = self.request.user

        return (
            user.is_authenticated
            and user.is_active
            and user.role == self.required_role
        )


class HomeRedirectView(LoginRequiredMixin, View):
    """Redirect users to their role-specific dashboard."""

    def get(self, request, *args, **kwargs):
        return redirect(request.user.dashboard_url_name)


class DashboardView(RoleRequiredMixin, TemplateView):
    template_name = "accounts/dashboard.html"
    required_role = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        context["role"] = user.role
        context["role_label"] = user.get_role_display()
        context["role_summary"] = ROLE_SUMMARY.get(
            user.role,
            "Welcome to your internal procurement workspace.",
        )

        context["can_manage_users"] = user.has_perm(
            "accounts.view_user"
        )

        can_view_requisitions = user.has_perm(
            "requisitions.view_requisition"
        )
        can_view_inventory = user.has_perm(
            "inventory.view_inventoryitem"
        )

        requisitions = Requisition.objects.none()
        inventory_items = InventoryItem.objects.none()

        if can_view_requisitions:
            requisitions = Requisition.objects.select_related(
                "requested_by", "department"
            )

            if user.role == User.Role.EMPLOYEE:
                requisitions = requisitions.filter(requested_by=user)

        if can_view_inventory:
            inventory_items = InventoryItem.objects.filter(
                is_active=True
            )

        low_stock = inventory_items.filter(
            quantity_on_hand__lte=models.F("reorder_level")
        )

        if user.role == User.Role.ADMINISTRATOR:
            stats = [
                {
                    "label": "Active Users",
                    "value": User.objects.filter(is_active=True).count(),
                },
                {
                    "label": "Departments",
                    "value": Department.objects.filter(is_active=True).count(),
                },
                {
                    "label": "Requisitions",
                    "value": requisitions.count(),
                },
                {
                    "label": "Low Stock Items",
                    "value": low_stock.count(),
                },
            ]

        elif user.role == User.Role.EMPLOYEE:
            stats = [
                {
                    "label": "My Requisitions",
                    "value": requisitions.count(),
                },
                {
                    "label": "Submitted",
                    "value": requisitions.filter(
                        status="submitted"
                    ).count(),
                },
                {
                    "label": "Approved",
                    "value": requisitions.filter(
                        status="approved"
                    ).count(),
                },
                {
                    "label": "Fulfilled",
                    "value": requisitions.filter(
                        status="fulfilled"
                    ).count(),
                },
            ]

        elif user.role == User.Role.MANAGER:
            stats = [
                {
                    "label": "Total Requisitions",
                    "value": requisitions.count(),
                },
                {
                    "label": "Awaiting Review",
                    "value": requisitions.filter(
                        status="submitted"
                    ).count(),
                },
                {
                    "label": "Approved",
                    "value": requisitions.filter(
                        status="approved"
                    ).count(),
                },
                {
                    "label": "Rejected",
                    "value": requisitions.filter(
                        status="rejected"
                    ).count(),
                },
            ]

        elif user.role == User.Role.INVENTORY_STAFF:
            stats = [
                {
                    "label": "Active Items",
                    "value": inventory_items.count(),
                },
                {
                    "label": "Low Stock Items",
                    "value": low_stock.count(),
                },
                {
                    "label": "Approved Requests",
                    "value": requisitions.filter(
                        status="approved"
                    ).count(),
                },
                {
                    "label": "Partially Fulfilled",
                    "value": requisitions.filter(
                        status="partially_fulfilled"
                    ).count(),
                },
            ]

        elif user.role == User.Role.PURCHASING_STAFF:
            pending_purchase_requests = PurchaseRequest.objects.filter(
                status=PurchaseRequest.Status.PENDING
            )

            pending_items_count = PurchaseRequestItem.objects.filter(
                purchase_request__status=PurchaseRequest.Status.PENDING
            ).count()

            stats = [
                {
                    "label": "Pending Purchase Requests",
                    "value": pending_purchase_requests.count(),
                },
                {
                    "label": "Items to Purchase",
                    "value": pending_items_count,
                },
                {
                    "label": "Active Items",
                    "value": inventory_items.count(),
                },
                {
                    "label": "Low Stock Items",
                    "value": low_stock.count(),
                },
            ]

            context["pending_purchase_requests"] = (
                pending_purchase_requests
                .select_related(
                    "requisition",
                    "requisition__requested_by",
                )
                .prefetch_related("items")
                .order_by("-created_at")[:8]
            )

        else:
            stats = [
                {
                    "label": "Active Items",
                    "value": inventory_items.count(),
                },
                {
                    "label": "Low Stock Items",
                    "value": low_stock.count(),
                },
            ]

        context["dashboard_stats"] = stats
        context["low_stock_items"] = low_stock[:5]
        context["recent_requisitions"] = (
            requisitions[:5] if can_view_requisitions else []
        )

        return context


class AdministratorDashboardView(DashboardView):
    template_name = "accounts/dashboards/administrator.html"
    required_role = User.Role.ADMINISTRATOR


class EmployeeDashboardView(DashboardView):
    template_name = "accounts/dashboards/employee.html"
    required_role = User.Role.EMPLOYEE


class ManagerDashboardView(DashboardView):
    template_name = "accounts/dashboards/manager.html"
    required_role = User.Role.MANAGER


class InventoryDashboardView(DashboardView):
    template_name = "accounts/dashboards/inventory_staff.html"
    required_role = User.Role.INVENTORY_STAFF


class PurchasingDashboardView(DashboardView):
    template_name = "accounts/dashboards/purchasing_staff.html"
    required_role = User.Role.PURCHASING_STAFF


class ReceivingDashboardView(DashboardView):
    template_name = "accounts/dashboards/receiving_staff.html"
    required_role = User.Role.RECEIVING_STAFF


class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    permission_required = "accounts.view_user"

    def get_queryset(self):
        return manageable_users(self.request.user)


class UserCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    CreateView,
):
    model = User
    form_class = UserCreateForm
    template_name = "accounts/form.html"
    permission_required = "accounts.add_user"
    success_url = reverse_lazy("user-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create User"
        context["submit_label"] = "Create User"
        context["cancel_url"] = reverse_lazy("user-list")
        return context

    def form_valid(self, form):
        messages.success(
            self.request,
            "User account created successfully.",
        )
        return super().form_valid(form)


class UserUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UpdateView,
):
    model = User
    form_class = UserUpdateForm
    template_name = "accounts/form.html"
    permission_required = "accounts.change_user"
    success_url = reverse_lazy("user-list")

    def get_queryset(self):
        return manageable_users(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Update User"
        context["submit_label"] = "Save Changes"
        context["cancel_url"] = reverse_lazy("user-list")
        return context

    def form_valid(self, form):
        messages.success(
            self.request,
            "User account updated successfully.",
        )
        return super().form_valid(form)


class UserPasswordView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    FormView,
):
    form_class = AdminPasswordChangeForm
    template_name = "accounts/form.html"
    permission_required = "accounts.change_user"
    success_url = reverse_lazy("user-list")

    def get_target_user(self):
        return get_object_or_404(
            manageable_users(self.request.user),
            pk=self.kwargs["pk"],
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.get_target_user()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Change User Password"
        context["submit_label"] = "Change Password"
        context["cancel_url"] = reverse_lazy("user-list")
        context["target_user"] = self.get_target_user()
        return context

    def form_valid(self, form):
        form.save()

        messages.success(
            self.request,
            "User password changed successfully.",
        )

        return super().form_valid(form)


def custom_permission_denied(request, exception=None):
    from django.shortcuts import render

    return render(request, "403.html", status=403)
