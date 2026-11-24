
from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from inventory.models import InventoryItem

from .models import ApprovalHistory, Requisition, RequisitionItem


class RequisitionForm(forms.ModelForm):
    class Meta:
        model = Requisition
        fields = ["purpose"]
        widgets = {
            "purpose": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Explain why these items are needed...",
                }
            ),
        }

    def clean_purpose(self):
        purpose = self.cleaned_data["purpose"].strip()

        if not purpose:
            raise forms.ValidationError(
                "Please provide the reason for this request."
            )

        return purpose


class RequisitionItemForm(forms.ModelForm):
    inventory_item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.none(),
        required=False,
        empty_label="Custom / Not in inventory",
        widget=forms.Select(
            attrs={"class": "form-select inventory-item-select"}
        ),
    )

    class Meta:
        model = RequisitionItem
        fields = [
            "inventory_item",
            "item_description",
            "unit_of_measure",
            "quantity_requested",
        ]
        widgets = {
            "item_description": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter item name",
                }
            ),
            "unit_of_measure": forms.Select(
                attrs={"class": "form-select"}
            ),
            "quantity_requested": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0.01",
                    "step": "0.01",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["inventory_item"].queryset = (
            InventoryItem.objects.filter(is_active=True)
            .select_related("category")
            .order_by("name")
        )

        self.fields["unit_of_measure"].choices = [
            ("", "Select unit"),
            *InventoryItem.Unit.choices,
        ]

    def clean(self):
        cleaned_data = super().clean()

        inventory_item = cleaned_data.get("inventory_item")
        description = (
            cleaned_data.get("item_description") or ""
        ).strip()
        unit = cleaned_data.get("unit_of_measure")

        if inventory_item:
            cleaned_data["item_description"] = inventory_item.name
            cleaned_data["unit_of_measure"] = (
                inventory_item.unit_of_measure
            )
        else:
            if not description:
                self.add_error(
                    "item_description",
                    "Enter the name of the requested item.",
                )

            if not unit:
                self.add_error(
                    "unit_of_measure",
                    "Select a unit of measurement.",
                )

        return cleaned_data


class BaseRequisitionItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        valid_items = 0
        selected_inventory_items = []

        for form in self.forms:
            if not form.cleaned_data:
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            inventory_item = form.cleaned_data.get("inventory_item")
            description = (
                form.cleaned_data.get("item_description") or ""
            ).strip()
            quantity = form.cleaned_data.get("quantity_requested")

            if not inventory_item and not description and not quantity:
                continue

            valid_items += 1

            if inventory_item:
                selected_inventory_items.append(inventory_item.pk)

        if valid_items < 1:
            raise forms.ValidationError(
                "Add at least one item to your requisition."
            )

        if len(selected_inventory_items) != len(
            set(selected_inventory_items)
        ):
            raise forms.ValidationError(
                "You cannot select the same inventory item twice."
            )


RequisitionItemFormSet = inlineformset_factory(
    Requisition,
    RequisitionItem,
    form=RequisitionItemForm,
    formset=BaseRequisitionItemFormSet,
    extra=1,
    can_delete=True,
    max_num=30,
    validate_max=True,
)

class RequisitionDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            ("approved", "Approve Requisition"),
            ("rejected", "Reject Requisition"),
        ],
        widget=forms.HiddenInput(),
    )

    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Enter remarks or reason for rejection...",
            }
        ),
    )

class TrackingFilterForm(forms.Form):
    search = forms.CharField(
        required=False,
        label="Request Number",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search REQ number...",
            }
        ),
    )

    status = forms.ChoiceField(
        required=False,
        choices=[("", "All Statuses"), *Requisition.Status.choices],
        widget=forms.Select(
            attrs={"class": "form-select"}
        ),
    )

    date_from = forms.DateField(
        required=False,
        label="From",
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    date_to = forms.DateField(
        required=False,
        label="To",
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        decision = cleaned_data.get("decision")
        remarks = (cleaned_data.get("remarks") or "").strip()

        if decision == "rejected" and not remarks:
            self.add_error(
                "remarks",
                "Remarks are required when rejecting a requisition.",
            )

        cleaned_data["remarks"] = remarks

        return cleaned_data

class ManagerFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Request Number",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search requisition number...",
            }
        ),
    )

    status = forms.ChoiceField(
        required=False,
        choices=[("", "All")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    date_from = forms.DateField(
        required=False,
        label="From",
        widget=forms.DateInput(
            attrs={"class": "form-control", "type": "date"}
        ),
    )

    date_to = forms.DateField(
        required=False,
        label="To",
        widget=forms.DateInput(
            attrs={"class": "form-control", "type": "date"}
        ),
    )

    mine = forms.BooleanField(
        required=False,
        label="Only my decisions",
        widget=forms.CheckboxInput(
            attrs={"class": "form-check-input"}
        ),
    )

    def __init__(
        self,
        *args,
        status_choices=None,
        status_label="Status",
        allow_mine=False,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        if status_choices is None:
            self.fields.pop("status")
        else:
            self.fields["status"].choices = [
                ("", "All"),
                *status_choices,
            ]
            self.fields["status"].label = status_label

        if not allow_mine:
            self.fields.pop("mine")

    def clean(self):
        cleaned_data = super().clean()

        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        if date_from and date_to and date_from > date_to:
            self.add_error(
                "date_to",
                "The end date cannot be earlier than the start date.",
            )

        return cleaned_data

    def filter_queryset(
        self,
        queryset,
        *,
        number="requisition_number",
        status="status",
        date="request_date",
    ):
        if not self.is_bound or not self.is_valid():
            return queryset

        data = self.cleaned_data

        if data.get("q"):
            queryset = queryset.filter(
                **{f"{number}__icontains": data["q"].strip()}
            )

        if data.get("status"):
            queryset = queryset.filter(
                **{status: data["status"]}
            )

        if data.get("date_from"):
            queryset = queryset.filter(
                **{f"{date}__gte": data["date_from"]}
            )

        if data.get("date_to"):
            queryset = queryset.filter(
                **{f"{date}__lte": data["date_to"]}
            )

        return queryset

class ApprovalDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=ApprovalHistory.Decision.choices,
        widget=forms.HiddenInput(),
    )

    remarks = forms.CharField(
        required=False,
        max_length=1000,
        label="Remarks",
        help_text="Remarks are required when rejecting a requisition.",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Enter your remarks or reason for rejection...",
                "maxlength": "1000",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        decision = cleaned_data.get("decision")
        remarks = (cleaned_data.get("remarks") or "").strip()

        if (
            decision == ApprovalHistory.Decision.REJECTED
            and not remarks
        ):
            self.add_error(
                "remarks",
                "Remarks are required when rejecting a requisition.",
            )

        cleaned_data["remarks"] = remarks

        return cleaned_data