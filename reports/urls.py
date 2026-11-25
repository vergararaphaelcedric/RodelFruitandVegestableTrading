
from django.urls import path

from .definitions import REPORTS
from .views import ReportExportView, ReportIndexView, ReportView


urlpatterns = [
    path(
        "reports/",
        ReportIndexView.as_view(),
        name="report-index",
    ),
]

for slug, report in REPORTS.items():
    urlpatterns.extend(
        [
            path(
                f"reports/{slug}/",
                ReportView.as_view(report=report),
                name=f"report-{slug}",
            ),
            path(
                f"reports/{slug}/export/",
                ReportExportView.as_view(report=report),
                name=f"report-{slug}-export",
            ),
        ]
    )
