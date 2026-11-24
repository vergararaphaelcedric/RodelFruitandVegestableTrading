
from django import forms

from .models import (
    BudgetApproval,
    PurchaseOrder,
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierQuotation,
)


class PurchaseRequestUpdateForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequest
        fields = ["status", "notes"]

        widgets = {
            "status": forms.Select(
                attrs={"class": "form-select"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Enter purchasing updates or remarks...",
                }
            ),
        }


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "name",
            "contact_person",
            "email",
            "phone",
            "address",
            "payment_terms",
            "notes",
            "is_active",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "contact_person": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control"}
            ),
            "phone": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
            "payment_terms": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())

        duplicate = Supplier.objects.filter(
            name__iexact=name
        )

        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)

        if duplicate.exists():
            raise forms.ValidationError(
                "A supplier with this name already exists."
            )

        return name


class SupplierQuotationForm(forms.ModelForm):
    class Meta:
        model = SupplierQuotation
        fields = [
            "supplier",
            "purchase_request_item",
            "quantity",
            "unit_price",
            "quotation_date",
            "valid_until",
            "remarks",
        ]

        widgets = {
            "supplier": forms.Select(
                attrs={"class": "form-select"}
            ),
            "purchase_request_item": forms.Select(
                attrs={"class": "form-select"}
            ),
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0.01",
                    "step": "0.01",
                }
            ),
            "unit_price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0.01",
                    "step": "0.01",
                }
            ),
            "quotation_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "valid_until": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "remarks": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["supplier"].queryset = Supplier.objects.filter(
            is_active=True
        ).order_by("name")

        self.fields["purchase_request_item"].queryset = (
            SupplierQuotation._meta.get_field(
                "purchase_request_item"
            ).remote_field.model.objects.filter(
                purchase_request__status=PurchaseRequest.Status.PENDING
            ).select_related(
                "purchase_request"
            ).order_by(
                "purchase_request__request_number",
                "item_description",
            )
        )

    def clean(self):
        cleaned_data = super().clean()

        quotation_date = cleaned_data.get("quotation_date")
        valid_until = cleaned_data.get("valid_until")

        if quotation_date and valid_until:
            if valid_until < quotation_date:
                self.add_error(
                    "valid_until",
                    "The validity date cannot be earlier than the quotation date.",
                )

        return cleaned_data

class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ("expected_delivery_date", "notes")
        widgets = {
            "expected_delivery_date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_expected_delivery_date(self):
        value = self.cleaned_data.get("expected_delivery_date")
        if value and value < self.instance.order_date:
            raise forms.ValidationError(
                "The delivery date cannot be earlier than the order date."
            )
        return value


class PurchaseOrderFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Search",
        max_length=100,
        widget=forms.TextInput(
            attrs={"placeholder": "PO, PR, REQ or supplier"}
        ),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "All"), *PurchaseOrder.Status.choices],
    )


class BudgetFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Search",
        max_length=30,
        widget=forms.TextInput(
            attrs={"placeholder": "PR- or REQ- number"}
        ),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "All"), *BudgetApproval.Status.choices],
    )


class ApprovalDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            ("approved", "Approve Budget"),
            ("rejected", "Reject Budget"),
        ],
        widget=forms.RadioSelect,
    )

    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Enter your decision remarks...",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        decision = cleaned_data.get("decision")
        remarks = cleaned_data.get("remarks", "").strip()

        if decision == "rejected" and not remarks:
            self.add_error(
                "remarks",
                "Remarks are required when rejecting a budget.",
            )

        cleaned_data["remarks"] = remarks
        return cleaned_data
