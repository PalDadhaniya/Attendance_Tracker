from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from accounts.models import Employee


# =====================================================
# ALLOWED IP RANGES
# =====================================================
class AllowedIPRange(models.Model):
    """
    Model to store allowed IP ranges for attendance operations.
    Supports both individual IPs and CIDR notation.
    """
    name = models.CharField(max_length=100, help_text="Descriptive name for this IP range (e.g., 'Office WiFi')")
    ip_range = models.CharField(max_length=50, help_text="IP range in CIDR notation (e.g., 192.168.1.0/24) or individual IP")
    is_active = models.BooleanField(default=True, help_text="Whether this IP range is currently active")
    description = models.TextField(blank=True, help_text="Optional description of where this IP range is used")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Allowed IP Range"
        verbose_name_plural = "Allowed IP Ranges"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.ip_range}"

    def contains_ip(self, ip_address):
        """
        Check if the given IP address is within this IP range.
        Supports both individual IPs and CIDR notation.
        """
        import ipaddress

        try:
            # Handle CIDR notation (e.g., 192.168.1.0/24)
            if '/' in self.ip_range:
                network = ipaddress.ip_network(self.ip_range, strict=False)
                ip = ipaddress.ip_address(ip_address)
                return ip in network
            else:
                # Handle individual IP
                return ip_address == self.ip_range
        except (ipaddress.AddressValueError, ValueError):
            # If there's any error parsing, return False for security
            return False


# =====================================================
# ATTENDANCE (ONE PER DAY)
# =====================================================
class Attendance(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="attendances"
    )
    date = models.DateField()
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("employee", "date")
        ordering = ["-date"]

    def session_duration(self):
        if self.check_in and self.check_out:
            return self.check_out - self.check_in
        return timedelta(0)

    def session_hours_display(self):
        duration = self.session_duration()
        total_seconds = int(duration.total_seconds())
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h}:{m:02d}:{s:02d}"

    def break_total_duration(self):
        total = timedelta(0)
        for br in self.breaks.all():
            if br.break_in and br.break_out:
                total += (br.break_out - br.break_in)
        return total

    def break_time_display(self):
        duration = self.break_total_duration()
        total_seconds = int(duration.total_seconds())
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h}:{m:02d}:{s:02d}"

    def working_duration(self):
        working = self.session_duration() - self.break_total_duration()
        return max(working, timedelta(0))

    def working_hours_display(self):
        duration = self.working_duration()
        total_seconds = int(duration.total_seconds())
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h}:{m:02d}:{s:02d}"

    def __str__(self):
        return f"{self.employee.employee_id} - {self.date}"


# =====================================================
# BREAKS
# =====================================================
class Break(models.Model):
    attendance = models.ForeignKey(
        Attendance,
        on_delete=models.CASCADE,
        related_name="breaks"
    )
    break_in = models.DateTimeField()
    break_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["break_in"]

    def duration(self):
        if self.break_in and self.break_out:
            return self.break_out - self.break_in
        return timedelta(0)

    def __str__(self):
        return f"Break - {self.attendance.employee.employee_id}"


# =====================================================
# LEAVE TYPE
# =====================================================
class LeaveType(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)
    is_paid = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# =====================================================
# LEAVE BALANCE
# =====================================================
class LeaveBalance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)

    total = models.PositiveIntegerField()
    used = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("0.0")
    )

    class Meta:
        unique_together = ("employee", "leave_type")

    @property
    def remaining(self):
        return Decimal(self.total) - self.used

    def __str__(self):
        return f"{self.employee.employee_id} - {self.leave_type.name}"


# =====================================================
# LEAVE REQUEST (FULL + HALF DAY)
# =====================================================
class LeaveRequest(models.Model):
    LEAVE_DURATION_CHOICES = (
        ("FULL", "Full Day"),
        ("HALF", "Half Day"),
    )

    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    )

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)

    start_date = models.DateField()
    end_date = models.DateField()

    duration_type = models.CharField(
        max_length=10,
        choices=LEAVE_DURATION_CHOICES,
        default="FULL"
    )

    total_days = models.DecimalField(
        max_digits=4,
        decimal_places=1
    )

    reason = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    applied_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.leave_type.name} ({self.total_days})"


# =====================================================
# COMPANY POLICY (PDF UPLOAD)
# =====================================================
class CompanyPolicy(models.Model):
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="policies/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# =====================================================
# COMPANY HOLIDAYS
# =====================================================
class CompanyHoliday(models.Model):
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.start_date} to {self.end_date} - {self.reason}"

