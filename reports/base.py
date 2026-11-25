
import csv
import io
from datetime import date, datetime
from decimal import Decimal


class Echo:
    """Small CSV buffer used for streaming CSV output."""

    def write(self, value):
        return value


def csv_lines(values):
    """
    Convert one row of values into a CSV line.

    Used by ReportExportView to stream CSV rows.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(values)
    return buffer.getvalue()


def format_cell(value):
    """Convert values into readable CSV-compatible text."""

    if value is None:
        return ""

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if hasattr(value, "all") and callable(value.all):
        return ", ".join(
            str(item)
            for item in value.all()
        )

    if hasattr(value, "get_full_name"):
        full_name = value.get_full_name()

        if full_name:
            return full_name

    return str(value)
