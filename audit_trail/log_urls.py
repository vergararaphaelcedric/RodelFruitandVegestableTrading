from django.urls import path

from audit_trail.log_views import AuditLogListView


app_name = "audit_trail"

urlpatterns = [
    path(
        "",
        AuditLogListView.as_view(),
        name="log_list",
    ),
]