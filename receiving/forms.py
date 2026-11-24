
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory


class DeliveryReceiptForm(forms.Form):
    delivery_note_number = forms.CharField(
        max_length=100,
        required=False,
        label="Supplier Delivery Note Number",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter delivery note number",
        }),
    )

    remarks = forms.CharField(
        required=False,
        label="Receiving Remarks",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Enter general delivery remarks...",
        }),
    )


class DeliveryReceiptItemForm(forms.Form):
    purchase_order_item_id = forms.IntegerField(
        widget=forms.HiddenInput()
    )

    delivered_quantity = forms.DecimalField(
        label="Delivered Quantity",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "step": "0.01",
        }),
    )

    accepted_quantity = forms.DecimalField(
        label="Accepted Quantity",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "step": "0.01",
        }),
    )

    damaged_quantity = forms.DecimalField(
        label="Damaged Quantity",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "step": "0.01",
        }),
    )

    incorrect_quantity = forms.DecimalField(
        label="Incorrect Quantity",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "step": "0.01",
        }),
    )

    damaged_description = forms.CharField(
        required=False,
        label="Damaged Item Description",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Describe damaged items",
        }),
    )

    incorrect_description = forms.CharField(
        required=False,
        label="Incorrect Item Description",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Describe incorrect items",
        }),
    )

    def clean(self):
        cleaned_data = super().clean()

        delivered = cleaned_data.get("delivered_quantity")
        accepted = cleaned_data.get("accepted_quantity")
        damaged = cleaned_data.get("damaged_quantity")
        incorrect = cleaned_data.get("incorrect_quantity")

        if None in (delivered, accepted, damaged, incorrect):
            return cleaned_data

        if delivered == 0:
            if accepted != 0 or damaged != 0 or incorrect != 0:
                raise ValidationError(
                    "Accepted, damaged, and incorrect quantities "
                    "must all be zero when nothing was delivered."
                )

            return cleaned_data

        if accepted + damaged + incorrect != delivered:
            raise ValidationError(
                "Delivered quantity must equal accepted quantity "
                "+ damaged quantity + incorrect quantity."
            )

        if damaged > 0 and not cleaned_data.get("damaged_description"):
            self.add_error(
                "damaged_description",
                "Describe the damaged items.",
            )

        if incorrect > 0 and not cleaned_data.get("incorrect_description"):
            self.add_error(
                "incorrect_description",
                "Describe the incorrect items.",
            )

        return cleaned_data


class BaseDeliveryReceiptItemFormSet(BaseFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        has_delivery = False

        for form in self.forms:
            if not form.cleaned_data:
                continue

            delivered = form.cleaned_data.get(
                "delivered_quantity",
                Decimal("0"),
            )

            if delivered > 0:
                has_delivery = True

        if not has_delivery:
            raise ValidationError(
                "Enter at least one delivered item."
            )


DeliveryReceiptItemFormSet = formset_factory(
    DeliveryReceiptItemForm,
    formset=BaseDeliveryReceiptItemFormSet,
    extra=0,
)


from .models import DeliveryDiscrepancy


class DeliveryDiscrepancyResolutionForm(forms.ModelForm):

    class Meta:
        model = DeliveryDiscrepancy

        fields = [
            "supplier_reference",
            "status",
            "promised_replacement_date",
            "resolution_notes",
        ]

        widgets = {
            "supplier_reference": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter supplier reference number",
            }),

            "status": forms.Select(attrs={
                "class": "form-select",
            }),

            "promised_replacement_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),

            "resolution_notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Enter supplier response or resolution details...",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()

        status = cleaned_data.get("status")
        promised_date = cleaned_data.get(
            "promised_replacement_date"
        )
        resolution_notes = cleaned_data.get(
            "resolution_notes",
            "",
        )

        if (
            status == DeliveryDiscrepancy.Status.REPLACEMENT_PROMISED
            and not promised_date
        ):
            self.add_error(
                "promised_replacement_date",
                "Enter the supplier's promised replacement date.",
            )

        if status in {
            DeliveryDiscrepancy.Status.REPLACED,
            DeliveryDiscrepancy.Status.CREDITED,
            DeliveryDiscrepancy.Status.CLOSED,
        } and not resolution_notes.strip():
            self.add_error(
                "resolution_notes",
                "Resolution notes are required.",
            )

        return cleaned_data