
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.core.exceptions import PermissionDenied, ValidationError

from .models import (
    ApprovalHistory,
    Requisition,
    RequisitionItem,
    StatusHistory,
    StockReservation,
)
from .services import change_status, decide_requisition


# --------------------------------------------------
# REQUISITION ITEM INLINE
# --------------------------------------------------

class RequisitionItemInline(admin.TabularInline):
    model = RequisitionItem
    extra = 1
    autocomplete_fields = ("inventory_item",)
    readonly_fields = ("created_at", "updated_at")

    fields = (
        "inventory_item",
        "item_description",
        "unit_of_measure",
        "quantity_requested",
        "quantity_fulfilled",
        "created_at",
        "updated_at",
    )


# --------------------------------------------------
# READ-ONLY HISTORY INLINE
# --------------------------------------------------

class ReadOnlyHistoryMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StatusHistoryInline(ReadOnlyHistoryMixin, admin.TabularInline):
    model = StatusHistory
    extra = 0
    can_delete = False
    readonly_fields = (
        "previous_status",
        "new_status",
        "changed_by",
        "remarks",
        "changed_at",
    )

    fields = (
        "previous_status",
        "new_status",
        "changed_by",
        "remarks",
        "changed_at",
    )


class ApprovalHistoryInline(ReadOnlyHistoryMixin, admin.TabularInline):
    model = ApprovalHistory
    extra = 0
    can_delete = False
    readonly_fields = (
        "approver",
        "decision",
        "remarks",
        "previous_status",
        "new_status",
        "status_history",
        "acted_at",
    )

    fields = (
        "approver",
        "decision",
        "remarks",
        "previous_status",
        "new_status",
        "status_history",
        "acted_at",
    )


# --------------------------------------------------
# ACTION FORM
# --------------------------------------------------

class DecisionActionForm(ActionForm):
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Enter remarks for this action...",
            }
        ),
        label="Remarks",
    )


# --------------------------------------------------
# REQUISITION ADMIN
# --------------------------------------------------

@admin.register(Requisition)
class RequisitionAdmin(admin.ModelAdmin):
    action_form = DecisionActionForm

    list_display = (
        "requisition_number",
        "requested_by",
        "department",
        "request_date",
        "status",
        "item_count",
    )

    list_filter = (
        "status",
        "department",
        "request_date",
    )

    search_fields = (
        "requisition_number",
        "purpose",
        "requested_by__username",
        "requested_by__first_name",
        "requested_by__last_name",
    )

    list_select_related = (
        "requested_by",
        "department",
    )

    autocomplete_fields = (
        "requested_by",
        "department",
    )

    readonly_fields = (
        "requisition_number",
        "status",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Requisition Information",
            {
                "fields": (
                    "requisition_number",
                    "requested_by",
                    "department",
                    "request_date",
                    "purpose",
                    "status",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    inlines = (
        RequisitionItemInline,
        StatusHistoryInline,
        ApprovalHistoryInline,
    )

    actions = (
        "submit_selected",
        "approve_selected",
        "reject_selected",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("requested_by", "department")
            .prefetch_related("items")
        )

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)

        if request.user.is_authenticated:
            initial.setdefault("requested_by", request.user.pk)

            department_id = getattr(
                request.user,
                "department_id",
                None,
            )

            if department_id:
                initial.setdefault("department", department_id)

        return initial

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None

        super().save_model(request, obj, form, change)

        if is_new:
            StatusHistory.objects.create(
                requisition=obj,
                previous_status="",
                new_status=obj.status,
                changed_by=request.user,
                remarks="Requisition created.",
            )

    # ----------------------------------------------
    # PERMISSION CHECK FOR APPROVAL ACTIONS
    # ----------------------------------------------

    def has_approve_permission(self, request):
        return (
            request.user.is_active
            and request.user.has_perm(
                "requisitions.approve_requisition"
            )
        )

    # ----------------------------------------------
    # COMMON ACTION PROCESSOR
    # ----------------------------------------------

    def _run(self, request, queryset, callback, success_verb):
        remarks = request.POST.get("remarks", "").strip()

        successful = 0
        failed = 0

        for requisition in queryset:
            try:
                callback(requisition, remarks)
                successful += 1

            except (PermissionDenied, ValidationError) as exc:
                failed += 1

                self.message_user(
                    request,
                    f"{requisition.requisition_number}: {exc}",
                    level=messages.ERROR,
                )

        if successful:
            self.message_user(
                request,
                f"{successful} requisition(s) {success_verb}.",
                level=messages.SUCCESS,
            )

        if failed:
            self.message_user(
                request,
                f"{failed} requisition(s) could not be processed.",
                level=messages.WARNING,
            )

    # ----------------------------------------------
    # SUBMIT ACTION
    # ----------------------------------------------

    @admin.action(description="Submit selected requisitions")
    def submit_selected(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda req, remarks: change_status(
                req,
                Requisition.Status.SUBMITTED,
                request.user,
                remarks,
            ),
            "submitted",
        )

    # ----------------------------------------------
    # APPROVE ACTION
    # ----------------------------------------------

    @admin.action(
        description="Approve selected requisitions",
        permissions=["approve"],
    )
    def approve_selected(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda req, remarks: decide_requisition(
                req,
                request.user,
                ApprovalHistory.Decision.APPROVED,
                remarks,
            ),
            "approved",
        )

    # ----------------------------------------------
    # REJECT ACTION
    # ----------------------------------------------

    @admin.action(
        description="Reject selected requisitions",
        permissions=["approve"],
    )
    def reject_selected(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda req, remarks: decide_requisition(
                req,
                request.user,
                ApprovalHistory.Decision.REJECTED,
                remarks,
            ),
            "rejected",
        )


# --------------------------------------------------
# STATUS HISTORY ADMIN (READ-ONLY)
# --------------------------------------------------

@admin.register(StatusHistory)
class StatusHistoryAdmin(ReadOnlyHistoryMixin, admin.ModelAdmin):
    list_display = (
        "requisition",
        "previous_status",
        "new_status",
        "changed_by",
        "changed_at",
    )

    list_filter = (
        "new_status",
        "changed_at",
    )

    search_fields = (
        "requisition__requisition_number",
        "changed_by__username",
        "remarks",
    )

    readonly_fields = (
        "requisition",
        "previous_status",
        "new_status",
        "changed_by",
        "remarks",
        "changed_at",
    )


# --------------------------------------------------
# APPROVAL HISTORY ADMIN (READ-ONLY)
# --------------------------------------------------

@admin.register(ApprovalHistory)
class ApprovalHistoryAdmin(ReadOnlyHistoryMixin, admin.ModelAdmin):
    list_display = (
        "requisition",
        "approver",
        "decision",
        "acted_at",
    )

    list_filter = (
        "decision",
        "acted_at",
    )

    search_fields = (
        "requisition__requisition_number",
        "approver__username",
        "remarks",
    )

    readonly_fields = (
        "requisition",
        "approver",
        "decision",
        "remarks",
        "previous_status",
        "new_status",
        "status_history",
        "acted_at",
    )

# --------------------------------------------------
# STOCK RESERVATION ADMIN (READ-ONLY)
# --------------------------------------------------

@admin.register(StockReservation)
class StockReservationAdmin(ReadOnlyHistoryMixin, admin.ModelAdmin):

    list_display = (
        "requisition_item",
        "inventory_item",
        "quantity_requested",
        "quantity_reserved",
        "status",
        "reserved_by",
        "created_at",
        "released_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "requisition_item__requisition__requisition_number",
        "inventory_item__item_code",
        "inventory_item__name",
        "reserved_by__username",
    )

    list_select_related = (
        "requisition_item__requisition",
        "inventory_item",
        "reserved_by",
    )

    readonly_fields = (
        "requisition_item",
        "inventory_item",
        "quantity_requested",
        "quantity_reserved",
        "status",
        "reserved_by",
        "created_at",
        "released_at",
    )

    ordering = (
        "-created_at",
        "-id",
    )
