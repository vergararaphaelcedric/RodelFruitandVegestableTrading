
from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Department, User


class DepartmentRequiredMixin:
    """Require users to belong to an active department."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "department" in self.fields:
            self.fields["department"].required = True
            self.fields["department"].queryset = Department.objects.filter(
                is_active=True
            )

    def clean_department(self):
        department = self.cleaned_data.get("department")

        if department is None:
            raise forms.ValidationError(
                "Please select a department."
            )

        if not department.is_active:
            raise forms.ValidationError(
                "Please select an active department."
            )

        return department


class UserCreateForm(DepartmentRequiredMixin, UserCreationForm):

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "employee_id",
            "phone",
            "department",
            "role",
        )

    def save(self, commit=True):
        user = super().save(commit=False)

        # Only administrators receive Django Admin staff access.
        user.is_staff = (
            user.role == User.Role.ADMINISTRATOR
        )

        if commit:
            user.save()

        return user


class UserUpdateForm(DepartmentRequiredMixin, forms.ModelForm):

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "employee_id",
            "phone",
            "department",
            "role",
            "is_active",
        )

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Prevent users from changing their own role or account status.
        if (
            request_user
            and self.instance.pk == request_user.pk
        ):
            self.fields["role"].disabled = True
            self.fields["is_active"].disabled = True

    def save(self, commit=True):
        user = super().save(commit=False)

        # Keep Django Admin access synchronized with the role.
        user.is_staff = (
            user.is_superuser
            or user.role == User.Role.ADMINISTRATOR
        )

        if commit:
            user.save()

        return user
