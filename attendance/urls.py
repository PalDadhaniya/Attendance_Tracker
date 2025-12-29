from django.urls import path
from . import views

urlpatterns = [

    # ======================
    # EMPLOYEE (SELF)
    # ======================
    path("dashboard/", views.dashboard, name="dashboard"),
    path("check-in/", views.check_in, name="check_in"),
    path("check-out/", views.check_out, name="check_out"),
    path("break-in/", views.break_in, name="break_in"),
    path("break-out/", views.break_out, name="break_out"),

    path("leave/apply/", views.apply_leave, name="apply_leave"),
    path("leave/<int:leave_id>/edit/", views.edit_leave, name="edit_leave"),
    path("leave/<int:leave_id>/delete/", views.delete_leave, name="delete_leave"),
    path("leave/status/", views.leave_status, name="leave_status"),
    path("leaves/", views.employee_leaves, name="employee_leaves"),
    path("monthly-report/", views.employee_monthly_report, name="employee_monthly_report"),
    path("attendance-history/", views.employee_attendance_history, name="employee_attendance_history"),

    # Company info (Employee)
    path("company-policies/", views.employee_company_policies, name="employee_company_policies"),
    path("holidays/", views.employee_company_holidays, name="employee_company_holidays"),

    # ======================
    # ADMIN (CUSTOM PANEL)
    # ======================
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),

    # Employees
    path(
        "admin-dashboard/employees/",
        views.admin_view_employees,
        name="admin_view_employees",
    ),
    path(
        "admin-dashboard/employee/add/",
        views.admin_add_employee,
        name="admin_add_employee",
    ),
    path(
        "admin-dashboard/employee/<str:employee_id>/details/",
        views.admin_employee_details,
        name="admin_employee_details",
    ),
    path(
        "admin-dashboard/employee/<str:employee_id>/attendance/",
        views.admin_employee_attendance,
        name="admin_employee_attendance",
    ),
    path(
        "admin-dashboard/employee/<str:employee_id>/attendance/<int:attendance_id>/edit/",
        views.admin_edit_attendance,
        name="admin_edit_attendance",
    ),
    path(
    "admin-dashboard/employee/<str:employee_id>/overview/",
    views.admin_employee_overview,
    name="admin_employee_overview",
    ),
    path(
    "admin-dashboard/employee/<str:employee_id>/monthly-report/",
    views.admin_employee_monthly_report,
    name="admin_employee_monthly_report",
    ),
    path(
    "admin-dashboard/employee/<str:employee_id>/delete/",
    views.delete_employee,
    name="delete_employee",
    ),


    # Leaves (Admin)
    path(
        "admin-dashboard/leaves/",
        views.admin_leave_requests,
        name="admin_leave_requests",
    ),
    path(
        "admin-dashboard/leave/<int:leave_id>/<str:status>/",
        views.admin_update_leave_status,
        name="admin_update_leave_status",
    ),

    # Company info (Admin)
    path(
        "admin-dashboard/company-policies/",
        views.admin_company_policies,
        name="admin_company_policies",
    ),
    path(
    "admin-dashboard/holidays/",
    views.admin_company_holidays,
    name="admin_company_holidays",
    ),
    path(
    "admin-dashboard/ip-ranges/",
    views.admin_ip_ranges,
    name="admin_ip_ranges",
    ),
    path(
    "login-redirect/",
    views.login_redirect,
    name="login_redirect",
    ),
    path("redirect/", views.login_redirect, name="login_redirect"),
    path(
        "admin-dashboard/attendance-history/",
        views.admin_attendance_history,
        name="admin_attendance_history",
    ),
]