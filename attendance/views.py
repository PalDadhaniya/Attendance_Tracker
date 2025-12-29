from decimal import Decimal
from datetime import timedelta, datetime, time, date

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages

from accounts.models import Employee
from .models import (
    Attendance,
    Break,
    LeaveType,
    LeaveBalance,
    LeaveRequest,
    CompanyPolicy,
    CompanyHoliday,
)

# ======================================================
# HELPERS
# ======================================================

def is_admin(user):
    return user.is_staff


def validate_office_network_ip(request):
    """
    Validate that the client IP is from the office network (192.168.1.x).
    Returns True if valid, False if not. Shows error messages as needed.
    """
    # Debug: Print all IP-related headers
    print("=== IP DETECTION DEBUG ===")
    print(f"REMOTE_ADDR: {request.META.get('REMOTE_ADDR')}")
    print(f"HTTP_X_FORWARDED_FOR: {request.META.get('HTTP_X_FORWARDED_FOR')}")
    print(f"HTTP_X_REAL_IP: {request.META.get('HTTP_X_REAL_IP')}")
    print(f"HTTP_X_FORWARDED: {request.META.get('HTTP_X_FORWARDED')}")
    print(f"HTTP_FORWARDED: {request.META.get('HTTP_FORWARDED')}")
    print(f"HTTP_HOST: {request.META.get('HTTP_HOST')}")
    print(f"SERVER_NAME: {request.META.get('SERVER_NAME')}")
    print("==========================")

    # Try multiple headers to find the real client IP
    client_ip = None

    # Priority order for IP detection (most reliable first)
    ip_headers = [
        'HTTP_X_REAL_IP',           # Real IP from reverse proxy
        'HTTP_X_FORWARDED_FOR',     # Forwarded by proxy/load balancer
        'HTTP_X_FORWARDED',         # Older forwarded header
        'HTTP_FORWARDED',           # RFC 7239 forwarded header
        'REMOTE_ADDR'               # Direct connection (may be localhost in dev)
    ]

    for header in ip_headers:
        ip_value = request.META.get(header)
        if ip_value:
            # Handle comma-separated IPs (take the first/original IP)
            if ',' in ip_value:
                ip_value = ip_value.split(',')[0].strip()
            if ip_value and ip_value != '127.0.0.1' and not ip_value.startswith('127.'):
                client_ip = ip_value
                print(f"Found valid IP from {header}: {client_ip}")
                break

    # If we still don't have a real IP, try REMOTE_ADDR as last resort
    if not client_ip:
        client_ip = request.META.get('REMOTE_ADDR')
        print(f"Using REMOTE_ADDR as fallback: {client_ip}")

    if not client_ip:
        messages.error(request, "Unable to detect your network IP address. Please contact administrator.")
        return False

    print(f"Final client_ip for validation: {client_ip}")

    # DEVELOPMENT MODE: Allow localhost for testing when on office network
    # Check if user is actually on office network by checking their network interface
    import socket
    try:
        # Try multiple methods to get local IP
        local_ip = None

        # Method 1: socket.gethostbyname(socket.gethostname())
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            print(f"Method 1 - Local machine IP: {local_ip}")
        except:
            pass

        # Method 2: Get IP from network interfaces
        if not local_ip or local_ip.startswith('127.'):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))  # Connect to Google DNS
                local_ip = s.getsockname()[0]
                s.close()
                print(f"Method 2 - Local machine IP: {local_ip}")
            except Exception as e:
                print(f"Method 2 failed: {e}")

        # Method 3: Check all network interfaces
        if not local_ip or local_ip.startswith('127.'):
            try:
                import netifaces
                for interface in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr['addr']
                            if not ip.startswith('127.') and ip != '::1':
                                local_ip = ip
                                print(f"Method 3 - Found IP on {interface}: {local_ip}")
                                break
                        if local_ip and not local_ip.startswith('127.'):
                            break
            except ImportError:
                print("netifaces not available, using basic detection")

        print(f"Final local machine IP: {local_ip}")

        # If local machine is on office network, allow localhost for development
        if local_ip and local_ip.startswith('192.168.1.'):
            print("Development mode: Local machine is on office network, allowing localhost")
            if client_ip in ['127.0.0.1', '::1'] or client_ip.startswith('127.'):
                print("Allowing localhost for development testing")
                return True
    except Exception as e:
        print(f"Error checking local IP: {e}")

    # Remove localhost/private IPs that shouldn't be used for validation
    if client_ip in ['127.0.0.1', '::1'] or client_ip.startswith('127.'):
        messages.error(request, f"Detected localhost IP ({client_ip}). Please ensure you're connected to the office network (192.168.1.x) and try again.")
        return False

    # Check against allowed IP ranges in database
    from .models import AllowedIPRange

    allowed_ranges = AllowedIPRange.objects.filter(is_active=True)
    ip_allowed = False

    for ip_range in allowed_ranges:
        if ip_range.contains_ip(client_ip):
            ip_allowed = True
            print(f"IP {client_ip} allowed by range: {ip_range.name} ({ip_range.ip_range})")
            break

    if not ip_allowed:
        # Create error message with list of allowed ranges
        allowed_range_names = [f"{r.name} ({r.ip_range})" for r in allowed_ranges]
        if allowed_range_names:
            range_list = ", ".join(allowed_range_names)
            messages.error(request, f"Access denied. Your IP ({client_ip}) is not in any allowed network range. Allowed ranges: {range_list}. Please connect to an authorized network.")
        else:
            messages.error(request, f"Access denied. Your IP ({client_ip}) is not in any allowed network range. No network ranges are currently configured.")
        return False

    print(f"IP validation successful: {client_ip}")
    return True


def auto_checkout_if_date_changed(employee):
    """
    If an employee forgot to check out and the date has changed,
    automatically check them out at the end of that day.
    Also closes any active break(s) for that attendance.
    """
    today = timezone.localdate()
    tz = timezone.get_current_timezone()

    stale_attendances = Attendance.objects.filter(
        employee=employee,
        check_out__isnull=True,
        date__lt=today,
    ).prefetch_related("breaks")

    if not stale_attendances.exists():
        return []

    closed_dates = []
    with transaction.atomic():
        for att in stale_attendances:
            end_of_day = timezone.make_aware(
                datetime.combine(att.date, time(23, 59, 59)),
                tz,
            )
            att.check_out = end_of_day
            att.save(update_fields=["check_out"])
            closed_dates.append(att.date)

            # Close any open breaks so calculations stay consistent
            att.breaks.filter(break_out__isnull=True).update(break_out=end_of_day)

    return closed_dates


# ======================================================
# LOGIN REDIRECT
# ======================================================

@login_required
def login_redirect(request):
    if request.user.is_staff:
        return redirect("admin_dashboard")
    return redirect("dashboard")


# ======================================================
# EMPLOYEE DASHBOARD
# ======================================================

@login_required
def dashboard(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, "employee/no_employee.html")
    
    if not employee.is_active:
        messages.error(request, "Your employee account is inactive. Please contact administrator.")
        return render(request, "employee/no_employee.html", {
            "message": "Your employee account is inactive. Please contact administrator."
        })

    # ✅ Auto check-out if date changed (missed check-out)
    closed_dates = auto_checkout_if_date_changed(employee)
    if closed_dates:
        # show most recent first
        closed_dates = sorted(closed_dates, reverse=True)
        if len(closed_dates) == 1:
            messages.info(
                request,
                f"You were auto checked out for {closed_dates[0]}.",
            )
        else:
            dates_text = ", ".join(str(d) for d in closed_dates)
            messages.info(
                request,
                f"You were auto checked out for these dates: {dates_text}.",
            )
    
    today = timezone.localdate()

    attendance = Attendance.objects.filter(
        employee=employee, date=today
    ).prefetch_related("breaks").first()

    # Calculate monthly summaries for the last 3 months
    monthly_summaries = []
    for i in range(3): # Current month and two previous months
        # Calculate the month and year for i months ago
        target_month = today.month - i
        target_year = today.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1

        current_month = date(target_year, target_month, 1)

        # Determine month end
        if current_month.month == 12:
            month_end = date(current_month.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(current_month.year, current_month.month + 1, 1) - timedelta(days=1)

        # Get attendance records for the month
        month_attendance_records = Attendance.objects.filter(
            employee=employee,
            date__gte=current_month,
            date__lte=month_end
        ).prefetch_related('breaks')

        # Get approved leave days for the month
        # A leave overlaps with the month if it doesn't end before the month starts
        # AND doesn't start after the month ends
        approved_leaves = LeaveRequest.objects.filter(
            employee=employee,
            status="APPROVED"
        ).exclude(
            end_date__lt=current_month  # Leave ends before month starts
        ).exclude(
            start_date__gt=month_end  # Leave starts after month ends
        )

        total_days_month = month_attendance_records.count()
        present_days_month = month_attendance_records.filter(check_out__isnull=False).count()

        leave_days_month = 0
        for leave in approved_leaves:
            if leave.duration_type == "HALF":
                # For half-day leaves, check if the leave date is within the month
                if current_month <= leave.start_date <= month_end:
                    leave_days_month += 0.5
            else:  # FULL day leave
                # Calculate overlapping days for full-day leaves
                leave_start = max(leave.start_date, current_month)
                leave_end = min(leave.end_date, month_end)
                if leave_start <= leave_end:
                    leave_days_month += (leave_end - leave_start).days + 1

        # Calculate working days in the month (excluding weekends and holidays if needed)
        # For now, we'll use total_days as working days, but this can be enhanced
        working_days_month = total_days_month

        absent_days_month = working_days_month - present_days_month - leave_days_month
        absent_days_month = max(0, absent_days_month) # Ensure no negative absent days

        total_hours_month = timedelta()
        for record in month_attendance_records:
            if record.check_out and record.check_in:
                work_duration = record.check_out - record.check_in
                break_duration = timedelta()
                for break_record in record.breaks.all():
                    if break_record.break_out and break_record.break_in:
                        break_duration += break_record.break_out - break_record.break_in
                total_hours_month += work_duration - break_duration
        
        working_days_month = total_days_month - leave_days_month
        attendance_rate_month = (present_days_month / working_days_month * 100) if working_days_month > 0 else 0

        monthly_summaries.append({
            'month_name': current_month.strftime('%B %Y'),
            'month_value': current_month.month,
            'year_value': current_month.year,
            'total_days': total_days_month,
            'present_days': present_days_month,
            'absent_days': absent_days_month,
            'leave_days': leave_days_month,
            'total_hours': total_hours_month,
            'attendance_rate': round(attendance_rate_month, 1),
        })

    return render(
        request,
        "employee/dashboard.html",
        {"attendance": attendance, "monthly_summaries": monthly_summaries},
    )


# ======================================================
# CHECK IN / CHECK OUT
# ======================================================

@login_required
def check_in(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "Employee profile not found. Please contact administrator.")
        return redirect("dashboard")

    if not employee.is_active:
        messages.error(request, "Your employee account is inactive. Please contact administrator.")
        return redirect("dashboard")

    # Validate office network access
    if not validate_office_network_ip(request):
        return redirect("dashboard")

    # ✅ Auto check-out if date changed (missed check-out)
    closed_dates = auto_checkout_if_date_changed(employee)
    if closed_dates:
        closed_dates = sorted(closed_dates, reverse=True)
        if len(closed_dates) == 1:
            messages.info(
                request,
                f"You were auto checked out for {closed_dates[0]}.",
            )
        else:
            dates_text = ", ".join(str(d) for d in closed_dates)
            messages.info(
                request,
                f"You were auto checked out for these dates: {dates_text}.",
            )
    
    today = timezone.localdate()

    Attendance.objects.get_or_create(
        employee=employee,
        date=today,
        defaults={"check_in": timezone.now()},
    )

    messages.success(request, "Checked in successfully!")
    return redirect("dashboard")


@login_required
def check_out(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "Employee profile not found. Please contact administrator.")
        return redirect("dashboard")

    if not employee.is_active:
        messages.error(request, "Your employee account is inactive. Please contact administrator.")
        return redirect("dashboard")

    # Validate office network access
    if not validate_office_network_ip(request):
        return redirect("dashboard")

    today = timezone.localdate()

    attendance = Attendance.objects.filter(
        employee=employee, date=today
    ).first()

    if attendance and not attendance.check_out:
        attendance.check_out = timezone.now()
        attendance.save()
        messages.success(request, "Checked out successfully!")
    elif not attendance:
        messages.error(request, "Please check in first before checking out.")
    else:
        messages.info(request, "You have already checked out today.")

    return redirect("dashboard")


# ======================================================
# BREAK IN / BREAK OUT
# ======================================================

@login_required
def break_in(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "Employee profile not found. Please contact administrator.")
        return redirect("dashboard")

    if not employee.is_active:
        messages.error(request, "Your employee account is inactive. Please contact administrator.")
        return redirect("dashboard")

    # Validate office network access
    if not validate_office_network_ip(request):
        return redirect("dashboard")

    # ✅ Auto check-out if date changed (missed check-out)
    closed_dates = auto_checkout_if_date_changed(employee)
    if closed_dates:
        closed_dates = sorted(closed_dates, reverse=True)
        if len(closed_dates) == 1:
            messages.info(
                request,
                f"You were auto checked out for {closed_dates[0]}.",
            )
        else:
            dates_text = ", ".join(str(d) for d in closed_dates)
            messages.info(
                request,
                f"You were auto checked out for these dates: {dates_text}.",
            )
    
    today = timezone.localdate()

    attendance = Attendance.objects.filter(
        employee=employee, date=today
    ).first()

    if not attendance:
        messages.error(request, "Please check in first before taking a break.")
        return redirect("dashboard")

    if attendance and not attendance.breaks.filter(break_out__isnull=True).exists():
        Break.objects.create(attendance=attendance, break_in=timezone.now())
        messages.success(request, "Break started!")
    else:
        messages.info(request, "You already have an active break. Please end it first.")

    return redirect("dashboard")


@login_required
def break_out(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "Employee profile not found. Please contact administrator.")
        return redirect("dashboard")

    if not employee.is_active:
        messages.error(request, "Your employee account is inactive. Please contact administrator.")
        return redirect("dashboard")

    # Validate office network access
    if not validate_office_network_ip(request):
        return redirect("dashboard")

    today = timezone.localdate()

    attendance = Attendance.objects.filter(
        employee=employee, date=today
    ).first()

    if not attendance:
        messages.error(request, "Please check in first.")
        return redirect("dashboard")

    current_break = attendance.breaks.filter(break_out__isnull=True).last()
    if current_break:
        current_break.break_out = timezone.now()
        current_break.save()
        messages.success(request, "Break ended!")
    else:
        messages.info(request, "No active break to end.")

    return redirect("dashboard")


# ======================================================
# APPLY LEAVE
# ======================================================

@login_required
def apply_leave(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, "employee/no_employee.html")
    
    if not employee.is_active:
        return render(request, "employee/no_employee.html", {
            "message": "Your employee account is inactive. Please contact administrator."
        })
    
    # Ensure default leave types exist
    if not LeaveType.objects.exists():
        LeaveType.objects.get_or_create(code="SL", defaults={"name": "Sick Leave", "is_paid": True})
        LeaveType.objects.get_or_create(code="CL", defaults={"name": "Casual Leave", "is_paid": True})
        LeaveType.objects.get_or_create(code="AL", defaults={"name": "Annual Leave", "is_paid": True})
        LeaveType.objects.get_or_create(code="PL", defaults={"name": "Personal Leave", "is_paid": True})
        LeaveType.objects.get_or_create(code="UL", defaults={"name": "Unpaid Leave", "is_paid": False})
    
    leave_types = LeaveType.objects.all()

    if request.method == "POST":
        leave_type = get_object_or_404(LeaveType, id=request.POST["leave_type"])
        start_date = request.POST["start_date"]
        end_date = request.POST.get("end_date") or start_date
        duration_type = request.POST["duration_type"]
        reason = request.POST["reason"]

        if duration_type == "HALF":
            total_days = Decimal("0.5")
        else:
            start = timezone.datetime.fromisoformat(start_date).date()
            end = timezone.datetime.fromisoformat(end_date).date()
            total_days = Decimal((end - start).days + 1)

        # ✅ Employee can apply any leave type
        #    Status will be PENDING – admin will approve / reject later
        LeaveRequest.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            duration_type=duration_type,
            total_days=total_days,
            reason=reason,
            # status stays default "PENDING"
        )

        messages.success(
            request,
            "Leave request submitted successfully and is waiting for admin approval.",
        )
        return redirect("leave_status")

    return render(request, "employee/apply_leave.html", {"leave_types": leave_types})


@login_required
def edit_leave(request, leave_id):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, "employee/no_employee.html")

    if not employee.is_active:
        return render(request, "employee/no_employee.html", {
            "message": "Your employee account is inactive. Please contact administrator."
        })

    # Get the leave request to edit
    leave_request = get_object_or_404(LeaveRequest, id=leave_id, employee=employee)

    # Only allow editing if status is PENDING
    if leave_request.status != "PENDING":
        messages.error(request, "You can only edit pending leave requests.")
        return redirect("leave_status")

    # Ensure default leave types exist
    if not LeaveType.objects.exists():
        LeaveType.objects.get_or_create(code="SL", defaults={"name": "Sick Leave", "is_paid": True})
        LeaveType.objects.get_or_create(code="CL", defaults={"name": "Casual Leave", "is_paid": True})
        LeaveType.objects.get_or_create(code="AL", defaults={"name": "Annual Leave", "is_paid": True})
        LeaveType.objects.get_or_create(code="PL", defaults={"name": "Personal Leave", "is_paid": True})
        LeaveType.objects.get_or_create(code="UL", defaults={"name": "Unpaid Leave", "is_paid": False})

    leave_types = LeaveType.objects.all()

    if request.method == "POST":
        leave_type = get_object_or_404(LeaveType, id=request.POST["leave_type"])
        start_date = request.POST["start_date"]
        end_date = request.POST.get("end_date") or start_date
        duration_type = request.POST["duration_type"]
        reason = request.POST["reason"]

        if duration_type == "HALF":
            total_days = Decimal("0.5")
        else:
            start = timezone.datetime.fromisoformat(start_date).date()
            end = timezone.datetime.fromisoformat(end_date).date()
            total_days = Decimal((end - start).days + 1)

        # Update the existing leave request
        leave_request.leave_type = leave_type
        leave_request.start_date = start_date
        leave_request.end_date = end_date
        leave_request.duration_type = duration_type
        leave_request.total_days = total_days
        leave_request.reason = reason
        leave_request.save()

        messages.success(request, "Leave request updated successfully!")
        return redirect("leave_status")

    # Pre-populate form with existing data
    initial_data = {
        'leave_type': leave_request.leave_type.id,
        'start_date': leave_request.start_date.isoformat(),
        'end_date': leave_request.end_date.isoformat() if leave_request.start_date != leave_request.end_date else '',
        'duration_type': leave_request.duration_type,
        'reason': leave_request.reason,
    }

    return render(request, "employee/apply_leave.html", {
        "leave_types": leave_types,
        "editing": True,
        "leave_request": leave_request,
        "initial_data": initial_data
    })


@login_required
def delete_leave(request, leave_id):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, "employee/no_employee.html")

    if not employee.is_active:
        return render(request, "employee/no_employee.html", {
            "message": "Your employee account is inactive. Please contact administrator."
        })

    # Get the leave request to delete
    leave_request = get_object_or_404(LeaveRequest, id=leave_id, employee=employee)

    # Only allow deletion if status is PENDING
    if leave_request.status != "PENDING":
        messages.error(request, "You can only delete pending leave requests.")
        return redirect("leave_status")

    # Delete the leave request
    leave_request.delete()

    messages.success(request, "Leave request deleted successfully.")
    return redirect("leave_status")


@login_required
def leave_status(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, "employee/no_employee.html")
    
    if not employee.is_active:
        return render(request, "employee/no_employee.html", {
            "message": "Your employee account is inactive. Please contact administrator."
        })

    leaves = LeaveRequest.objects.filter(employee=employee).select_related("leave_type")
    balances = LeaveBalance.objects.filter(employee=employee).select_related("leave_type")

    return render(
        request,
        "employee/leave_status.html",
        {"leaves": leaves, "balances": balances},
    )


# ======================================================
# ADMIN DASHBOARD
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    employees = Employee.objects.select_related("user").order_by("employee_id")

    # Determine which employees are "active" today (checked in and not checked out)
    today = timezone.localdate()
    todays_attendance = Attendance.objects.filter(
        employee__in=employees,
        date=today,
    ).values("employee_id", "check_out")

    active_employee_ids = {
        item["employee_id"]
        for item in todays_attendance
        if item["check_out"] is None  # checked in and still working
    }

    # Count pending leave requests
    pending_leave_requests = LeaveRequest.objects.filter(status="PENDING").count()

    # Determine greeting based on current time
    current_hour = timezone.now().hour
    if current_hour < 12:
        greeting = "Good Morning"
    elif current_hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    return render(
        request,
        "admin_panel/dashboard.html",
        {
            "employees": employees,
            "active_employee_ids": list(active_employee_ids),
            "pending_leave_requests": pending_leave_requests,
            "greeting": greeting,
        },
    )


# ======================================================
# COMPANY POLICIES (ADMIN)
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_company_policies(request):
    if request.method == "POST":
        # Delete policy
        delete_id = request.POST.get("delete_policy_id")
        if delete_id:
            policy = get_object_or_404(CompanyPolicy, id=delete_id)
            policy.delete()
            messages.success(request, "Company policy deleted successfully.")
            return redirect("admin_company_policies")

        title = request.POST.get("title", "").strip()
        file = request.FILES.get("file")

        if not title or not file:
            messages.error(request, "Title and PDF file are required.")
        else:
            CompanyPolicy.objects.create(title=title, file=file)
            messages.success(request, "Company policy uploaded successfully.")
            return redirect("admin_company_policies")

    policies = CompanyPolicy.objects.order_by("-uploaded_at")
    return render(
        request,
        "admin_panel/company_policies.html",
        {"policies": policies},
    )


# ======================================================
# ALLOWED IP RANGES (ADMIN)
# ======================================================



# ======================================================
# COMPANY HOLIDAYS (ADMIN)
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_company_holidays(request):
    if request.method == "POST":
        # Delete holiday
        delete_id = request.POST.get("delete_holiday_id")
        if delete_id:
            holiday = get_object_or_404(CompanyHoliday, id=delete_id)
            holiday.delete()
            messages.success(request, "Holiday deleted successfully.")
            return redirect("admin_company_holidays")

        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date") or start_date
        reason = request.POST.get("reason", "").strip()

        if not start_date or not reason:
            messages.error(request, "Start date and reason are required.")
        else:
            CompanyHoliday.objects.create(
                start_date=start_date,
                end_date=end_date,
                reason=reason,
            )
            messages.success(request, "Holiday added successfully.")
            return redirect("admin_company_holidays")

    holidays = CompanyHoliday.objects.all()
    return render(
        request,
        "admin_panel/company_holidays.html",
        {"holidays": holidays},
    )


# ======================================================
# COMPANY POLICIES (EMPLOYEE VIEW)
# ======================================================

@login_required
def employee_company_policies(request):
    policies = CompanyPolicy.objects.order_by("-uploaded_at")
    return render(
        request,
        "employee/company_policies.html",
        {"policies": policies},
    )


# ======================================================
# COMPANY HOLIDAYS (EMPLOYEE VIEW)
# ======================================================

@login_required
def employee_company_holidays(request):
    holidays = CompanyHoliday.objects.all()
    return render(
        request,
        "employee/holidays.html",
        {"holidays": holidays},
    )


# ======================================================
# ADMIN – ADD EMPLOYEE (FIXED & WORKING)
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_add_employee(request):
    if request.method == "POST":
        employee_id = request.POST["employee_id"].strip()
        name = request.POST["name"].strip()
        role = request.POST["role"]
        department = request.POST["department"]
        joining_date = request.POST["joining_date"]
        salary = request.POST["salary"]
        password = request.POST["password"].strip()

        # ❌ block admin username
        if employee_id.lower() == "admin":
            return render(request, "admin_panel/add_employee.html", {
                "error": "Employee ID cannot be admin"
            })

        # ❌ duplicate user
        if User.objects.filter(username=employee_id).exists():
            return render(request, "admin_panel/add_employee.html", {
                "error": "Employee ID already exists"
            })

        # Check if password is provided
        if not password:
            return render(request, "admin_panel/add_employee.html", {
                "error": "Password is required"
            })

        # Validate password
        try:
            validate_password(password)
        except ValidationError as e:
            error_messages = []
            for error in e.messages:
                error_messages.append(error)
            return render(request, "admin_panel/add_employee.html", {
                "error": "Password validation failed: " + " ".join(error_messages)
            })

        first_name, *last = name.split(" ", 1)
        last_name = last[0] if last else ""

        try:
            with transaction.atomic():
                # ✅ CREATE LOGIN USER with proper password hashing
                user = User.objects.create_user(
                    username=employee_id,     # LOGIN ID
                    password=password,        # This will be automatically hashed
                    first_name=first_name,
                    last_name=last_name,
                    is_staff=False,
                    is_active=True            # Ensure user is active for login
                )

                # ✅ CREATE EMPLOYEE PROFILE
                Employee.objects.create(
                    user=user,
                    employee_id=employee_id,
                    role=role,
                    department=department,
                    joining_date=joining_date,
                    salary=salary
                )

            return redirect("admin_view_employees")
        except ValidationError as e:
            # If password validation fails during user creation
            error_messages = []
            for error in e.messages:
                error_messages.append(error)
            return render(request, "admin_panel/add_employee.html", {
                "error": "Error creating user: " + " ".join(error_messages)
            })
        except Exception as e:
            # If user creation fails, clean up and show error
            return render(request, "admin_panel/add_employee.html", {
                "error": f"Error creating employee: {str(e)}"
            })

    return render(request, "admin_panel/add_employee.html")

# ======================================================
# ADMIN – VIEW ALL EMPLOYEES
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_view_employees(request):
    # Get search query from request
    search_query = request.GET.get('search', '').strip()

    # Filter employees based on search query
    employees = Employee.objects.select_related("user")

    if search_query:
        employees = employees.filter(
            models.Q(employee_id__icontains=search_query) |
            models.Q(user__first_name__icontains=search_query) |
            models.Q(user__last_name__icontains=search_query) |
            models.Q(role__icontains=search_query) |
            models.Q(department__icontains=search_query)
        )

    employees = employees.order_by("employee_id")
    return render(request, "admin_panel/employees.html", {
        "employees": employees,
        "search_query": search_query
    })


# ======================================================
# ADMIN – EDIT EMPLOYEE
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_employee_details(request, employee_id):
    employee = get_object_or_404(Employee, employee_id=employee_id)

    if request.method == "POST":
        employee.user.first_name = request.POST.get("first_name", "").strip()
        employee.user.last_name = request.POST.get("last_name", "").strip()
        employee.user.save()

        employee.role = request.POST.get("role", "").strip()
        employee.department = request.POST.get("department", "").strip()
        
        # Only update joining_date if a value is provided
        joining_date = request.POST.get("joining_date", "").strip()
        if joining_date:
            employee.joining_date = joining_date
        
        # Only update salary if a value is provided
        salary = request.POST.get("salary", "").strip()
        if salary:
            try:
                employee.salary = salary
            except (ValueError, TypeError):
                messages.error(request, "Invalid salary value.")
                return render(request, "admin_panel/employee_details.html", {"employee": employee})
        
        employee.save()
        messages.success(request, "Employee details updated successfully!")
        return redirect("admin_view_employees")

    return render(request, "admin_panel/employee_details.html", {"employee": employee})


# ======================================================
# ADMIN – EMPLOYEE ATTENDANCE
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_employee_attendance(request, employee_id):
    employee = get_object_or_404(Employee, employee_id=employee_id)

    attendance_history = Attendance.objects.filter(
        employee=employee
    ).prefetch_related("breaks").order_by("-date")

    return render(
        request,
        "admin_panel/employee_attendance.html",
        {
            "employee": employee,
            "attendance_history": attendance_history,
        },
    )


# ======================================================
# ADMIN – EDIT ATTENDANCE (MANIPULATE WORKING HOURS)
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_edit_attendance(request, employee_id, attendance_id):
    employee = get_object_or_404(Employee, employee_id=employee_id)
    attendance = get_object_or_404(
        Attendance.objects.prefetch_related("breaks"),
        id=attendance_id,
        employee=employee,
    )

    def _parse_dt(value: str):
        """
        Accepts HTML datetime-local strings like '2025-12-18T09:30'
        (or full ISO with seconds). Returns aware datetime in current TZ.
        """
        if not value:
            return None
        dt = parse_datetime(value)
        if dt is None:
            return None
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    if request.method == "POST":
        check_in_raw = request.POST.get("check_in", "").strip()
        check_out_raw = request.POST.get("check_out", "").strip()

        check_in = _parse_dt(check_in_raw)
        check_out = _parse_dt(check_out_raw) if check_out_raw else None

        if check_in is None:
            messages.error(request, "Invalid Check In datetime.")
            return render(
                request,
                "admin_panel/edit_attendance.html",
                {"employee": employee, "attendance": attendance},
            )

        if check_out is not None and check_out < check_in:
            messages.error(request, "Check Out cannot be earlier than Check In.")
            return render(
                request,
                "admin_panel/edit_attendance.html",
                {"employee": employee, "attendance": attendance},
            )

        attendance.check_in = check_in
        attendance.check_out = check_out
        attendance.save()

        # Update existing breaks (optional)
        for br in attendance.breaks.all():
            if request.POST.get(f"delete_break_{br.id}") == "on":
                br.delete()
                continue

            br_in = _parse_dt(request.POST.get(f"break_in_{br.id}", "").strip())
            br_out_raw = request.POST.get(f"break_out_{br.id}", "").strip()
            br_out = _parse_dt(br_out_raw) if br_out_raw else None

            if br_in is None:
                messages.error(request, f"Invalid Break In for break #{br.id}.")
                return render(
                    request,
                    "admin_panel/edit_attendance.html",
                    {"employee": employee, "attendance": attendance},
                )

            if br_out is not None and br_out < br_in:
                messages.error(request, f"Break Out cannot be earlier than Break In (break #{br.id}).")
                return render(
                    request,
                    "admin_panel/edit_attendance.html",
                    {"employee": employee, "attendance": attendance},
                )

            br.break_in = br_in
            br.break_out = br_out
            br.save()

        # Add new break (optional)
        new_break_in_raw = request.POST.get("new_break_in", "").strip()
        new_break_out_raw = request.POST.get("new_break_out", "").strip()
        if new_break_in_raw:
            new_break_in = _parse_dt(new_break_in_raw)
            new_break_out = _parse_dt(new_break_out_raw) if new_break_out_raw else None
            if new_break_in is None:
                messages.error(request, "Invalid New Break In datetime.")
                return render(
                    request,
                    "admin_panel/edit_attendance.html",
                    {"employee": employee, "attendance": attendance},
                )
            if new_break_out is not None and new_break_out < new_break_in:
                messages.error(request, "New Break Out cannot be earlier than New Break In.")
                return render(
                    request,
                    "admin_panel/edit_attendance.html",
                    {"employee": employee, "attendance": attendance},
                )
            Break.objects.create(
                attendance=attendance,
                break_in=new_break_in,
                break_out=new_break_out,
            )

        messages.success(request, "Attendance updated successfully.")
        return redirect("admin_employee_attendance", employee_id=employee.employee_id)

    return render(
        request,
        "admin_panel/edit_attendance.html",
        {"employee": employee, "attendance": attendance},
    )

# ======================================================
# ADMIN – EMPLOYEE OVERVIEW
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_employee_overview(request, employee_id):
    employee = get_object_or_404(Employee, employee_id=employee_id)

    attendance_history = Attendance.objects.filter(
        employee=employee
    ).prefetch_related("breaks").order_by("-date")

    leave_balances = LeaveBalance.objects.filter(employee=employee)
    leave_requests = LeaveRequest.objects.filter(employee=employee)

    return render(
        request,
        "admin_panel/employee_overview.html",
        {
            "employee": employee,
            "attendance_history": attendance_history,
            "leave_balances": leave_balances,
            "leave_requests": leave_requests,
        },
    )

# ======================================================
# ADMIN – LEAVE REQUESTS
# ======================================================

@login_required
@user_passes_test(is_admin)
@transaction.atomic
def admin_leave_requests(request):
    if request.method == "POST":
        delete_id = request.POST.get("delete_leave_id")
        if delete_id:
            leave = get_object_or_404(LeaveRequest, id=delete_id)
            
            # If the leave was approved, revert the used days from LeaveBalance
            if leave.status == "APPROVED":
                try:
                    balance = LeaveBalance.objects.select_for_update().get(
                        employee=leave.employee,
                        leave_type=leave.leave_type,
                    )
                    balance.used -= leave.total_days
                    balance.save()
                    messages.info(request, f"Leave balance for {leave.employee.user.get_full_name()} updated after deleting approved leave.")
                except LeaveBalance.DoesNotExist:
                    messages.warning(request, f"Could not find leave balance for {leave.employee.user.get_full_name()} to revert. Balance might be inconsistent.")
            
            leave.delete()
            messages.success(request, "Leave request deleted successfully.")
            return redirect("admin_leave_requests")

    leaves = LeaveRequest.objects.select_related(
        "employee", "leave_type"
    ).order_by("-applied_at")
    return render(request, "admin_panel/leave_requests.html", {"leaves": leaves})


@login_required
@user_passes_test(is_admin)
@transaction.atomic
def admin_update_leave_status(request, leave_id, status):
    leave = get_object_or_404(LeaveRequest, id=leave_id)

    if status == "APPROVED" and leave.status != "APPROVED":
        balance = LeaveBalance.objects.select_for_update().get(
            employee=leave.employee,
            leave_type=leave.leave_type,
        )
        balance.used += leave.total_days
        balance.save()

    leave.status = status
    leave.save()
    return redirect("admin_leave_requests")


# ======================================================
# ADMIN – DELETE EMPLOYEE (SAFE)
# ======================================================

@login_required
@user_passes_test(is_admin)
def delete_employee(request, employee_id):
    employee = get_object_or_404(Employee, employee_id=employee_id)

    Attendance.objects.filter(employee=employee).delete()
    LeaveRequest.objects.filter(employee=employee).delete()
    LeaveBalance.objects.filter(employee=employee).delete()

    employee.user.delete()  # cascades employee

    return redirect("admin_view_employees")


# ======================================================
# EMPLOYEE LEAVES
# ======================================================

@login_required
def employee_leaves(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, "employee/no_employee.html")
    
    if not employee.is_active:
        return render(request, "employee/no_employee.html", {
            "message": "Your employee account is inactive. Please contact administrator."
        })

    balances = LeaveBalance.objects.filter(employee=employee)
    leave_requests = LeaveRequest.objects.filter(employee=employee)

    return render(
        request,
        "employee/leaves.html",
        {
            "balances": balances,
            "leave_requests": leave_requests,
        },
    )


# ======================================================
# EMPLOYEE MONTHLY REPORT
# ======================================================

@login_required
@login_required
@user_passes_test(is_admin)
def admin_employee_monthly_report(request, employee_id):
    employee = get_object_or_404(Employee, employee_id=employee_id)

    # Get current month's attendance
    today = timezone.localdate()
    current_month_start = today.replace(day=1)

    # Get all attendance records for current month
    records = Attendance.objects.filter(
        employee=employee,
        date__gte=current_month_start,
        date__lte=today
    ).order_by("-date")

    # Calculate monthly statistics
    total_days = records.count()
    present_days = records.filter(check_out__isnull=False).count()
    absent_days = total_days - present_days

    # Calculate total working hours for the month
    total_hours = timedelta()
    for record in records:
        if record.check_out and record.check_in:
            check_duration = record.check_out - record.check_in
            # Subtract break time if any
            break_duration = timedelta()
            for break_record in record.breaks.all():
                if break_record.break_out and break_record.break_in:
                    break_duration += break_record.break_out - break_record.break_in
            total_hours += check_duration - break_duration

    # Format total hours for display
    total_seconds = int(total_hours.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    formatted_hours = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    context = {
        "employee": employee,
        "records": records,
        "month": today.strftime("%B %Y"),
        "total_days": total_days,
        "present_days": present_days,
        "absent_days": absent_days,
        "total_hours": formatted_hours,
        "is_admin_view": True,
    }

    return render(
        request,
        "employee/attendance_report.html",
        context,
    )


@login_required
@user_passes_test(is_admin)
def admin_ip_ranges(request):
    from .models import AllowedIPRange

    if request.method == "POST":
        # Handle delete action
        if 'delete_ip_range' in request.POST:
            ip_range_id = request.POST.get('delete_ip_range')
            try:
                ip_range = AllowedIPRange.objects.get(id=ip_range_id)
                ip_range.delete()
                messages.success(request, f"IP range '{ip_range.name}' deleted successfully.")
            except AllowedIPRange.DoesNotExist:
                messages.error(request, "IP range not found.")
            return redirect("admin_ip_ranges")

        # Handle add/edit action
        ip_range_id = request.POST.get('ip_range_id')
        name = request.POST.get('name', '').strip()
        ip_range = request.POST.get('ip_range', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if not name or not ip_range:
            messages.error(request, "Name and IP range are required.")
            return redirect("admin_ip_ranges")

        # Validate IP range format
        try:
            import ipaddress
            if '/' in ip_range:
                ipaddress.ip_network(ip_range, strict=False)
            else:
                ipaddress.ip_address(ip_range)
        except (ipaddress.AddressValueError, ValueError):
            messages.error(request, "Invalid IP range format. Use CIDR notation (e.g., 192.168.1.0/24) or individual IP address.")
            return redirect("admin_ip_ranges")

        if ip_range_id:
            # Edit existing
            try:
                ip_obj = AllowedIPRange.objects.get(id=ip_range_id)
                ip_obj.name = name
                ip_obj.ip_range = ip_range
                ip_obj.description = description
                ip_obj.is_active = is_active
                ip_obj.save()
                messages.success(request, f"IP range '{name}' updated successfully.")
            except AllowedIPRange.DoesNotExist:
                messages.error(request, "IP range not found.")
        else:
            # Create new
            AllowedIPRange.objects.create(
                name=name,
                ip_range=ip_range,
                description=description,
                is_active=is_active
            )
            messages.success(request, f"IP range '{name}' created successfully.")

        return redirect("admin_ip_ranges")

    # GET request - show the page
    ip_ranges = AllowedIPRange.objects.all().order_by('-created_at')
    return render(request, "admin_panel/ip_ranges.html", {
        "ip_ranges": ip_ranges,
        "title": "IP Range Management"
    })


def employee_monthly_report(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, "employee/no_employee.html")

    if not employee.is_active:
        return render(request, "employee/no_employee.html", {
            "message": "Your employee account is inactive. Please contact administrator."
        })

    # Get month and year from request parameters, default to current month/year
    today = timezone.localdate()
    selected_month = int(request.GET.get('month', today.month))
    selected_year = int(request.GET.get('year', today.year))

    # Create date range for selected month
    if selected_month == 12:
        month_start = date(selected_year, 12, 1)
        month_end = date(selected_year + 1, 1, 1) - timedelta(days=1)
    else:
        month_start = date(selected_year, selected_month, 1)
        month_end = date(selected_year, selected_month + 1, 1) - timedelta(days=1)

    # If selected month/year is current month/year, limit to today
    # Otherwise show the full month
    if selected_month == today.month and selected_year == today.year:
        end_date = today
    else:
        end_date = month_end

    # Get all attendance records for selected month
    records = Attendance.objects.filter(
        employee=employee,
        date__gte=month_start,
        date__lte=end_date
    ).order_by("-date")

    # Generate year options (from 2020 to current year + 1)
    current_year = today.year
    years = list(range(2020, current_year + 2))

    return render(
        request,
        "employee/attendance_report.html",
        {
            "records": records,
            "selected_month": selected_month,
            "selected_year": selected_year,
            "is_admin_view": False,
            "years": years,
        },
    )


# ======================================================
# EMPLOYEE - ATTENDANCE HISTORY (MONTHLY VIEW)
# ======================================================

@login_required
def employee_attendance_history(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, "employee/no_employee.html")

    if not employee.is_active:
        return render(request, "employee/no_employee.html", {
            "message": "Your employee account is inactive. Please contact administrator."
        })

    # Get the selected month and year from query parameters
    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')

    # Default to current month/year if not provided
    today = timezone.localdate()
    if not selected_month:
        selected_month = today.month
    else:
        selected_month = int(selected_month)

    if not selected_year:
        selected_year = today.year
    else:
        selected_year = int(selected_year)

    # Create date range for the selected month
    month_start = date(selected_year, selected_month, 1)
    if selected_month == 12:
        month_end = date(selected_year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(selected_year, selected_month + 1, 1) - timedelta(days=1)

    # Get all attendance records for the selected month
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__gte=month_start,
        date__lte=month_end
    ).prefetch_related('breaks').order_by('-date')

    # Get approved leave days for the month (needed for status calculation)
    approved_leaves = LeaveRequest.objects.filter(
        employee=employee,
        status="APPROVED",
        start_date__lte=month_end,
        end_date__gte=month_start
    )

    # Calculate break times and working hours for each record
    enhanced_records = []
    for record in attendance_records:
        record_data = {
            'record': record,
            'break_time': timedelta(),
            'working_hours': timedelta(),
            'break_details': [],
            'has_leave': False,
            'status': 'Absent'
        }

        # Calculate break time
        if record.check_in and record.check_out:
            for break_record in record.breaks.all():
                if break_record.break_out and break_record.break_in:
                    break_duration = break_record.break_out - break_record.break_in
                    record_data['break_time'] += break_duration
                    record_data['break_details'].append({
                        'start': break_record.break_in,
                        'end': break_record.break_out,
                        'duration': break_duration
                    })

            # Calculate working hours (check_out - check_in - break_time)
            work_duration = record.check_out - record.check_in
            record_data['working_hours'] = work_duration - record_data['break_time']
            record_data['status'] = 'Present'

        # Check if there's an approved leave for this date
        leave_on_date = approved_leaves.filter(
            start_date__lte=record.date,
            end_date__gte=record.date
        ).exists()

        if leave_on_date:
            record_data['has_leave'] = True
            record_data['status'] = 'On Leave'

        enhanced_records.append(record_data)

    # Group records by week
    weekly_records = []
    current_week = None
    week_data = None

    from collections import defaultdict

    for record_data in enhanced_records:
        record_date = record_data['record'].date
        week_number = record_date.isocalendar()[1]
        year = record_date.year
        
        # If this is a new week, create a new week_data
        if current_week != (year, week_number):
            if week_data:
                weekly_records.append(week_data)
            
            # Calculate week start and end dates
            week_start = record_date - timedelta(days=record_date.weekday())
            week_end = week_start + timedelta(days=6)
            
            week_data = {
                'week_number': week_number,
                'start_date': week_start,
                'end_date': week_end,
                'records': [],
                'total_hours': timedelta()
            }
            current_week = (year, week_number)
        
        week_data['records'].append(record_data)
        week_data['total_hours'] += record_data['working_hours']

    # Add the last week if it exists
    if week_data:
        weekly_records.append(week_data)

    # Sort weeks in descending order (most recent first)
    weekly_records.sort(key=lambda x: x['start_date'], reverse=True)

    # Calculate monthly statistics
    total_days = attendance_records.count()
    present_days = attendance_records.filter(check_out__isnull=False).count()

    # Calculate total leave days in the selected month
    leave_days = 0
    for leave in approved_leaves:
        # Calculate overlapping days between leave period and selected month
        leave_start = max(leave.start_date, month_start)
        leave_end = min(leave.end_date, month_end)
        if leave_start <= leave_end:
            leave_days += (leave_end - leave_start).days + 1

    # Calculate absent days (excluding approved leave days)
    absent_days = total_days - present_days - leave_days

    # Ensure absent_days doesn't go negative
    absent_days = max(0, absent_days)

    # Calculate total working hours for the month
    total_hours = timedelta()
    for record in attendance_records:
        if record.check_out and record.check_in:
            work_duration = record.check_out - record.check_in
            # Subtract break time if any
            break_duration = timedelta()
            for break_record in record.breaks.all():
                if break_record.break_out and break_record.break_in:
                    break_duration += break_record.break_out - break_record.break_in
            total_hours += work_duration - break_duration

    # Calculate attendance rate (excluding leave days)
    working_days = total_days - leave_days
    attendance_rate = (present_days / working_days * 100) if working_days > 0 else 0

    # Generate month options for the selector
    months = []
    for i in range(1, 13):
        months.append({
            'value': i,
            'name': date(2024, i, 1).strftime('%B'),
            'current': i == selected_month
        })

    # Generate year options (last 2 years to next year)
    years = []
    current_year = today.year
    for year in range(current_year - 2, current_year + 2):
        years.append({
            'value': year,
            'name': year,
            'current': year == selected_year
        })

    context = {
        'employee': employee,
        'enhanced_records': enhanced_records,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_name': date(selected_year, selected_month, 1).strftime('%B %Y'),
        'months': months,
        'years': years,
        'total_days': total_days,
        'present_days': present_days,
        'absent_days': absent_days,
        'leave_days': leave_days,
        'total_hours': total_hours,
        'attendance_rate': round(attendance_rate, 1),
        'weekly_records': weekly_records,
    }

    return render(request, 'employee/attendance_history.html', context)


# ======================================================
# ADMIN - ATTENDANCE HISTORY (MONTHLY VIEW)
# ======================================================

@login_required
@user_passes_test(is_admin)
def admin_attendance_history(request):
    # Get the selected month and year from query parameters
    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')

    # Default to current month/year if not provided
    today = timezone.localdate()
    if not selected_month:
        selected_month = today.month
    else:
        selected_month = int(selected_month)

    if not selected_year:
        selected_year = today.year
    else:
        selected_year = int(selected_year)

    # Create date range for the selected month
    month_start = date(selected_year, selected_month, 1)
    if selected_month == 12:
        month_end = date(selected_year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(selected_year, selected_month + 1, 1) - timedelta(days=1)

    # Get all attendance records for the selected month
    attendance_records = Attendance.objects.filter(
        date__gte=month_start,
        date__lte=month_end
    ).select_related('employee__user').prefetch_related('breaks').order_by('employee__employee_id', '-date')

    # Group records by employee
    employee_data = {}
    for record in attendance_records:
        emp_id = record.employee.employee_id
        if emp_id not in employee_data:
            employee_data[emp_id] = {
                'employee': record.employee,
                'records': [],
                'total_days': 0,
                'present_days': 0,
                'total_hours': timedelta(),
            }

        employee_data[emp_id]['records'].append(record)
        employee_data[emp_id]['total_days'] += 1

        # Count present days (has check_out)
        if record.check_out:
            employee_data[emp_id]['present_days'] += 1

            # Calculate working hours
            if record.check_in:
                work_duration = record.check_out - record.check_in

                # Subtract break time
                break_duration = timedelta()
                for break_record in record.breaks.all():
                    if break_record.break_out and break_record.break_in:
                        break_duration += break_record.break_out - break_record.break_in

                employee_data[emp_id]['total_hours'] += work_duration - break_duration

    # Calculate absent days and attendance rate for each employee
    for emp_data in employee_data.values():
        emp_data['absent_days'] = emp_data['total_days'] - emp_data['present_days']
        # Calculate attendance rate
        if emp_data['total_days'] > 0:
            emp_data['attendance_rate'] = round((emp_data['present_days'] / emp_data['total_days']) * 100, 1)
        else:
            emp_data['attendance_rate'] = 0.0

    # Convert employee_data to list for template
    employee_list = list(employee_data.values())

    # Calculate overall statistics
    total_employees = len(employee_list)
    total_present_days = sum(emp['present_days'] for emp in employee_list)
    total_working_days = sum(emp['total_days'] for emp in employee_list)
    overall_attendance_rate = (total_present_days / total_working_days * 100) if total_working_days > 0 else 0

    # Generate month options for the selector
    months = []
    for i in range(1, 13):
        months.append({
            'value': i,
            'name': date(2024, i, 1).strftime('%B'),
            'current': i == selected_month
        })

    # Generate year options (last 2 years to next year)
    years = []
    current_year = today.year
    for year in range(current_year - 2, current_year + 2):
        years.append({
            'value': year,
            'name': year,
            'current': year == selected_year
        })

    context = {
        'employee_list': employee_list,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'month_name': date(selected_year, selected_month, 1).strftime('%B %Y'),
        'months': months,
        'years': years,
        'total_employees': total_employees,
        'total_present_days': total_present_days,
        'total_working_days': total_working_days,
        'overall_attendance_rate': round(overall_attendance_rate, 1),
    }

    return render(request, 'admin_panel/attendance_history.html', context)

