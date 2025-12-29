from django.db import models
from django.contrib.auth.models import User

class Employee(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="employee_profile"
    )

    employee_id = models.CharField(max_length=20, unique=True)
    role = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    joining_date = models.DateField()
    salary = models.DecimalField(max_digits=10, decimal_places=2)

    is_active = models.BooleanField(default=True)  # ✅ REQUIRED

    def __str__(self):
        return self.employee_id