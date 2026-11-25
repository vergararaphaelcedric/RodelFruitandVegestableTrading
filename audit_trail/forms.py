from django import forms


class AuditLogFilterForm(forms.Form):
    search = forms.CharField(
        required=False,
        max_length=100,
        label="Search",
    )

    category = forms.CharField(
        required=False,
        max_length=50,
    )

    action = forms.CharField(
        required=False,
        max_length=100,
    )

    outcome = forms.CharField(
        required=False,
        max_length=30,
    )

    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )