
from django import template


register = template.Library()


@register.filter
def report_value(obj, accessor):
    """
    Resolve a report column accessor such as:
    status
    supplier__name
    inventory_item__name
    """
    if obj is None or not accessor:
        return "—"

    value = obj

    for part in str(accessor).split("__"):
        if value is None:
            return "—"

        if part == "pk":
            value = getattr(value, "pk", None)
        else:
            value = getattr(value, part, None)

    if value is None:
        return "—"

    if hasattr(value, "all") and callable(value.all):
        return ", ".join(str(item) for item in value.all())

    if hasattr(value, "get_full_name"):
        full_name = value.get_full_name()
        if full_name:
            return full_name

    return value
