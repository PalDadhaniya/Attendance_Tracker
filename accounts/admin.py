from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Employee
from attendance.models import Attendance


# =============================
# Attendance Inline
# =============================
class AttendanceInline(admin.TabularInline):
    model = Attendance
    extra = 0
    can_delete = False
    readonly_fields = ("date", "check_in", "check_out")


# =============================
# Employee Admin
# =============================
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "user")
    inlines = [AttendanceInline]
    actions = None  # ❌ NO BULK DELETE


# =============================
# USER ADMIN (CRITICAL FIX)
# =============================
class UserAdmin(DjangoUserAdmin):
    actions = None  # ❌ removes "Delete selected"

    def has_delete_permission(self, request, obj=None):
        return False  # ❌ removes delete button


# RE-REGISTER USER ADMIN
admin.site.unregister(User)
admin.site.register(User, UserAdmin)