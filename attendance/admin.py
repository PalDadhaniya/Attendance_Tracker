from django.contrib import admin
from .models import (
    Attendance,
    Break,
    LeaveRequest,
    LeaveType,
    LeaveBalance,
    CompanyPolicy,
    CompanyHoliday,
    AllowedIPRange,
)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "date",
        "check_in",
        "check_out",
        "session_hours_display",
        "break_time_display",
        "working_hours_display",
    )
    list_filter = ("date",)
    search_fields = ("employee__employee_id",)
    ordering = ("-date",)


@admin.register(Break)
class BreakAdmin(admin.ModelAdmin):
    list_display = ("attendance", "break_in", "break_out")
    ordering = ("-break_in",)


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_paid")


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "total", "used", "remaining")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "leave_type",
        "start_date",
        "end_date",
        "status",
        "applied_at",
    )
    list_filter = ("status", "leave_type")
    actions = ["approve_leave", "reject_leave"]

    def approve_leave(self, request, queryset):
        queryset.update(status="APPROVED")

    def reject_leave(self, request, queryset):
        queryset.update(status="REJECTED")

    approve_leave.short_description = "Approve selected leaves"
    reject_leave.short_description = "Reject selected leaves"


@admin.register(AllowedIPRange)
class AllowedIPRangeAdmin(admin.ModelAdmin):
    list_display = ("name", "ip_range", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "ip_range", "description")
    ordering = ("-created_at",)

    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "ip_range", "is_active")
        }),
        ("Additional Details", {
            "fields": ("description",),
            "classes": ("collapse",)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related()

