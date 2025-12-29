from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.apps import apps

from accounts.models import Employee
from .models import LeaveType, LeaveBalance


def create_default_leave_types():
    """Create default leave types if they don't exist"""
    default_leave_types = [
        {"code": "SL", "name": "Sick Leave", "is_paid": True},
        {"code": "CL", "name": "Casual Leave", "is_paid": True},
        {"code": "AL", "name": "Annual Leave", "is_paid": True},
        {"code": "PL", "name": "Personal Leave", "is_paid": True},
        {"code": "UL", "name": "Unpaid Leave", "is_paid": False},
    ]
    
    for lt_data in default_leave_types:
        LeaveType.objects.get_or_create(
            code=lt_data["code"],
            defaults={
                "name": lt_data["name"],
                "is_paid": lt_data["is_paid"]
            }
        )


@receiver(post_migrate)
def create_default_leave_types_on_migrate(sender, **kwargs):
    """Create default leave types after migrations"""
    if sender.name == 'attendance':
        create_default_leave_types()


@receiver(post_save, sender=Employee)
def create_leave_balances(sender, instance, created, **kwargs):
    if created:
        # Ensure default leave types exist
        create_default_leave_types()
        
        for lt in LeaveType.objects.all():
            LeaveBalance.objects.create(
                employee=instance,
                leave_type=lt,
                total=12 if lt.is_paid else 0
            )