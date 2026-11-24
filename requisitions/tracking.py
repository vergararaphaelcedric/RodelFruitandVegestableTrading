
"""Builds the progress steps shown on the tracking page."""

STEPS = [
    ("draft", "Created", "bi-file-earmark-plus"),
    ("submitted", "Pending approval", "bi-hourglass-split"),
    ("approved", "Approved", "bi-patch-check"),
    ("fulfilled", "Fulfilled", "bi-box-seam"),
]

RANK = {
    "draft": 0,
    "submitted": 1,
    "approved": 2,
    "partially_fulfilled": 3,
    "fulfilled": 3,
}

TERMINAL = {
    "rejected": ("Rejected", "bi-x-circle"),
    "cancelled": ("Cancelled", "bi-slash-circle"),
}


def _step(label, icon, state, when=None, note=""):
    return {
        "label": label,
        "icon": icon,
        "state": state,
        "when": when,
        "note": note,
    }


def _when(reached, key):
    if key == "fulfilled":
        return reached.get("fulfilled") or reached.get("partially_fulfilled")
    return reached.get(key)


def build_tracker(requisition, history):
    """Build progress steps using StatusHistory rows in chronological order."""
    reached = {}

    for row in history:
        reached.setdefault(row.new_status, row.changed_at)

    reached.setdefault("draft", requisition.created_at)
    status = requisition.status

    if status in TERMINAL:
        last = max(RANK[s] for s in reached if s in RANK)
        steps = []

        for key, label, icon in STEPS[:last + 1]:
            if key == "fulfilled" and "fulfilled" not in reached:
                label = "Partially fulfilled"

            steps.append(
                _step(label, icon, "done", _when(reached, key))
            )

        label, icon = TERMINAL[status]
        steps.append(
            _step(label, icon, "failed", reached.get(status))
        )

        return steps

    position = RANK[status]
    steps = []

    for index, (key, label, icon) in enumerate(STEPS):
        if status == "fulfilled" or index < position:
            state = "done"
        elif index == position:
            state = "current"
        else:
            state = "upcoming"

        note = (
            "Partially fulfilled"
            if state == "current" and status == "partially_fulfilled"
            else ""
        )

        when = _when(reached, key) if state != "upcoming" else None

        steps.append(
            _step(label, icon, state, when, note)
        )

    return steps
