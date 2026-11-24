from django import forms

from .models import InventoryItem, ItemCategory


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = [
            "name",
            "item_code",
            "category",
            "description",
            "unit_of_measure",
            "quantity_on_hand",
            "reorder_level",
            "is_durable_equipment",
            "is_active",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter item name",
                }
            ),
            "item_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: OFF-0001",
                }
            ),
            "category": forms.Select(
                attrs={"class": "form-select"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional item description",
                }
            ),
            "unit_of_measure": forms.Select(
                attrs={"class": "form-select"}
            ),
            "quantity_on_hand": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "step": "0.01",
                }
            ),
            "reorder_level": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "step": "0.01",
                }
            ),
            "is_durable_equipment": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["category"].queryset = (
            ItemCategory.objects.all().order_by("name")
        )


class ItemCategoryForm(forms.ModelForm):
    class Meta:
        model = ItemCategory
        fields = ["name", "description", "is_active"]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter category name",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional category description",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    
class InventoryRegistrationForm(forms.Form):
    inventory_item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.none(),
        required=False,
        label="Existing Inventory Item",
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )

    create_new_item = forms.BooleanField(
        required=False,
        label="Create a new inventory item",
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
    )

    name = forms.CharField(
        max_length=200,
        required=False,
        label="New Item Name",
        widget=forms.TextInput(attrs={
            "class": "form-control",
        }),
    )

    item_code = forms.CharField(
        max_length=30,
        required=False,
        label="New Item Code",
        widget=forms.TextInput(attrs={
            "class": "form-control",
        }),
    )

    category = forms.ModelChoiceField(
        queryset=ItemCategory.objects.none(),
        required=False,
        label="Category",
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )

    description = forms.CharField(
        required=False,
        label="Description",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
        }),
    )

    unit_of_measure = forms.ChoiceField(
        choices=InventoryItem.Unit.choices,
        required=False,
        initial=InventoryItem.Unit.PIECE,
        label="Unit of Measure",
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )

    reorder_level = forms.DecimalField(
        required=False,
        min_value=0,
        initial=0,
        label="Reorder Level",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "step": "0.01",
        }),
    )

    is_durable_equipment = forms.BooleanField(
        required=False,
        label="Durable Equipment",
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["inventory_item"].queryset = (
            InventoryItem.objects.filter(is_active=True).order_by("name")
        )

        self.fields["category"].queryset = (
            ItemCategory.objects.filter(is_active=True).order_by("name")
        )

    def clean(self):
        cleaned_data = super().clean()

        existing_item = cleaned_data.get("inventory_item")
        create_new = cleaned_data.get("create_new_item")

        if existing_item and create_new:
            raise forms.ValidationError(
                "Choose an existing item or create a new item, not both."
            )

        if not existing_item and not create_new:
            raise forms.ValidationError(
                "Select an existing item or choose to create a new item."
            )

        if create_new:
            required_fields = [
                "name",
                "item_code",
                "category",
                "unit_of_measure",
                "reorder_level",
            ]

            for field in required_fields:
                if not cleaned_data.get(field):
                    self.add_error(
                        field,
                        "This field is required when creating a new item.",
                    )

        return cleaned_data
