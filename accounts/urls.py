
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views


urlpatterns = [
    # Home and authentication
    path("", views.HomeRedirectView.as_view(), name="home"),

    # Audited login with failed-login tracking and lockout
    path(
        "login/",
        views.AuditedLoginView.as_view(),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),

    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url=reverse_lazy("home"),
        ),
        name="password-change",
    ),

    # Role-specific dashboards
    path(
        "dashboard/administrator/",
        views.AdministratorDashboardView.as_view(),
        name="dashboard-administrator",
    ),

    path(
        "dashboard/employee/",
        views.EmployeeDashboardView.as_view(),
        name="dashboard-employee",
    ),

    path(
        "dashboard/manager/",
        views.ManagerDashboardView.as_view(),
        name="dashboard-manager",
    ),

    path(
        "dashboard/inventory/",
        views.InventoryDashboardView.as_view(),
        name="dashboard-inventory",
    ),

    path(
        "dashboard/purchasing/",
        views.PurchasingDashboardView.as_view(),
        name="dashboard-purchasing",
    ),

    path(
        "dashboard/receiving/",
        views.ReceivingDashboardView.as_view(),
        name="dashboard-receiving",
    ),

    # User management
    path(
        "users/",
        views.UserListView.as_view(),
        name="user-list",
    ),

    path(
        "users/create/",
        views.UserCreateView.as_view(),
        name="user-create",
    ),

    path(
        "users/<int:pk>/edit/",
        views.UserUpdateView.as_view(),
        name="user-update",
    ),

    path(
        "users/<int:pk>/password/",
        views.UserPasswordView.as_view(),
        name="user-password",
    ),
]
