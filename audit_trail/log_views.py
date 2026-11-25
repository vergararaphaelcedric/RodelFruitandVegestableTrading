from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import render
from django.views import View

from audit_trail.forms import AuditLogFilterForm
from audit_trail.models import AuditLog


class AuditLogListView(
    LoginRequiredMixin,
    UserPassesTestMixin,
    View,
):
    template_name = "audit_trail/log_list.html"

    def test_func(self):
        user = self.request.user

        return (
            user.is_superuser
            or user.groups.filter(name="Administrator").exists()
        )

    def get(self, request):
        form = AuditLogFilterForm(request.GET or None)
        logs = AuditLog.objects.all()

        if form.is_valid():
            search = form.cleaned_data.get("search")
            category = form.cleaned_data.get("category")
            action = form.cleaned_data.get("action")
            outcome = form.cleaned_data.get("outcome")
            start_date = form.cleaned_data.get("start_date")
            end_date = form.cleaned_data.get("end_date")

            if search:
                logs = logs.filter(
                    Q(actor_username__icontains=search)
                    | Q(action__icontains=search)
                    | Q(description__icontains=search)
                )

            if category:
                logs = logs.filter(category__iexact=category)

            if action:
                logs = logs.filter(action__icontains=action)

            if outcome:
                logs = logs.filter(outcome__iexact=outcome)

            if start_date:
                logs = logs.filter(created_at__date__gte=start_date)

            if end_date:
                logs = logs.filter(created_at__date__lte=end_date)

        logs = logs[:200]

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "logs": logs,
            },
        )