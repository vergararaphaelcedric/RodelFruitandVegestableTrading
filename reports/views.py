
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.views import View

from accounts.models import User
from .base import csv_lines, format_cell
from .definitions import REPORTS


PAGE_SIZE = 15

TEXT_FIELD_TYPES = {
    "CharField",
    "TextField",
    "EmailField",
    "SlugField",
    "URLField",
}


def get_report_search_fields(model, columns):
    """
    Build searchable model field paths from report column accessors.
    Supports direct text fields and text fields on related models.
    """
    search_fields = []

    for column in columns:
        accessor = getattr(column, "accessor", "")

        if not accessor:
            continue

        current_model = model
        path_parts = str(accessor).split("__")

        try:
            for index, part in enumerate(path_parts):
                field = current_model._meta.get_field(part)
                field_path = "__".join(path_parts[: index + 1])

                if field.is_relation:
                    current_model = field.related_model

                    # If the column ends at a related object,
                    # search its text fields as well.
                    if index == len(path_parts) - 1:
                        for related_field in current_model._meta.get_fields():
                            if (
                                getattr(related_field, "concrete", False)
                                and not getattr(
                                    related_field,
                                    "many_to_many",
                                    False,
                                )
                                and not getattr(
                                    related_field,
                                    "one_to_many",
                                    False,
                                )
                                and related_field.get_internal_type()
                                in TEXT_FIELD_TYPES
                            ):
                                search_fields.append(
                                    f"{field_path}__{related_field.name}"
                                )

                elif field.get_internal_type() in TEXT_FIELD_TYPES:
                    search_fields.append(field_path)

        except (LookupError, AttributeError, TypeError):
            continue

    return list(dict.fromkeys(search_fields))


def apply_report_search(request, report, queryset):
    """
    Apply the search parameter to a report queryset.
    """
    search = request.GET.get("search", "").strip()

    if not search or not hasattr(queryset, "model"):
        return queryset

    search_fields = get_report_search_fields(
        queryset.model,
        report.columns,
    )

    if not search_fields:
        return queryset

    search_query = Q()

    for field_name in search_fields:
        search_query |= Q(
            **{f"{field_name}__icontains": search}
        )

    return queryset.filter(search_query).distinct()


class AdministratorRequiredMixin(
    LoginRequiredMixin,
    UserPassesTestMixin,
):
    """Allow access only to authenticated administrators."""

    def test_func(self):
        user = self.request.user

        return (
            user.is_authenticated
            and getattr(user, "role", None)
            == User.Role.ADMINISTRATOR
        )


class ReportIndexView(
    AdministratorRequiredMixin,
    View,
):
    template_name = "reports/index.html"

    def get(self, request, *args, **kwargs):
        context = {
            "reports": list(REPORTS.values()),
        }

        return render(
            request,
            self.template_name,
            context,
        )


class ReportView(
    AdministratorRequiredMixin,
    View,
):
    report = None
    template_name = "reports/report.html"

    def get_queryset(self, request):
        report = self.report

        if hasattr(report, "get_queryset"):
            queryset = report.get_queryset(request)

        elif hasattr(report, "queryset"):
            queryset = report.queryset

            if callable(queryset):
                queryset = queryset(request)

        else:
            queryset = []

        return apply_report_search(
            request,
            report,
            queryset,
        )

    def get(self, request, *args, **kwargs):
        report = self.report
        queryset = self.get_queryset(request)

        paginator = Paginator(
            queryset,
            PAGE_SIZE,
        )

        page_obj = paginator.get_page(
            request.GET.get("page", 1)
        )

        context = {
            "report": report,
            "columns": report.columns,
            "page_obj": page_obj,
            "rows": page_obj.object_list,
            "paginator": paginator,
            "filters_active": any(
                value
                for key, value in request.GET.items()
                if key != "page"
            ),
        }

        return render(
            request,
            self.template_name,
            context,
        )


class ReportExportView(
    AdministratorRequiredMixin,
    View,
):
    report = None

    def get_queryset(self, request):
        report = self.report

        if hasattr(report, "get_queryset"):
            queryset = report.get_queryset(request)

        else:
            queryset = getattr(
                report,
                "queryset",
                [],
            )

            if callable(queryset):
                queryset = queryset(request)

        return apply_report_search(
            request,
            report,
            queryset,
        )

    def get(self, request, *args, **kwargs):
        report = self.report
        queryset = self.get_queryset(request)

        filename = (
            f"{report.slug}-{date.today().isoformat()}.csv"
        )

        response = StreamingHttpResponse(
            self.generate_csv(report, queryset),
            content_type="text/csv; charset=utf-8",
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )

        return response

    def generate_csv(self, report, queryset):
        columns = report.columns

        header = [
            getattr(column, "label", str(column))
            for column in columns
        ]

        yield csv_lines(header)

        if hasattr(queryset, "iterator"):
            rows = queryset.iterator()
        else:
            rows = queryset

        for row in rows:
            values = []

            for column in columns:
                accessor = getattr(
                    column,
                    "accessor",
                    getattr(column, "key", ""),
                )

                value = row

                for part in str(accessor).split("__"):
                    if part:
                        value = getattr(
                            value,
                            part,
                            "",
                        )

                values.append(
                    format_cell(value)
                )

            yield csv_lines(values)
