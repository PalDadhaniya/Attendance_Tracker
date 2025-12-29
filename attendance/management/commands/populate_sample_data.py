from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import time, datetime, timedelta
from accounts.models import Employee
from attendance.models import Attendance, Break, AllowedIPRange
import random


class Command(BaseCommand):
    help = 'Populate sample attendance data for the current month'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=20,
            help='Number of days to populate (default: 20)',
        )

    def handle(self, *args, **options):
        self.stdout.write('Populating sample attendance data...')

        # Create default IP range if none exists
        if not AllowedIPRange.objects.exists():
            AllowedIPRange.objects.create(
                name="Office Network",
                ip_range="192.168.1.0/24",
                description="Default office WiFi network range",
                is_active=True
            )
            self.stdout.write(self.style.SUCCESS('Created default IP range: 192.168.1.0/24'))

        # Get all employees
        employees = Employee.objects.all()
        if not employees:
            self.stdout.write(self.style.ERROR('No employees found. Please add employees first.'))
            return

        days_to_populate = options['days']
        today = timezone.localdate()

        # Generate data for the last N days
        for days_back in range(days_to_populate, -1, -1):
            date = today - timedelta(days=days_back)

            # Skip weekends (optional - you can remove this if you want weekend data)
            if date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                continue

            for employee in employees:
                # 90% chance of attendance (simulate real-world attendance)
                if random.random() < 0.9:
                    # Generate realistic check-in time (between 8:30 AM and 9:30 AM)
                    check_in_hour = random.randint(8, 9)
                    check_in_minute = random.randint(30, 59) if check_in_hour == 8 else random.randint(0, 30)
                    check_in_time = time(check_in_hour, check_in_minute)

                    # Create check-in datetime
                    check_in_datetime = timezone.make_aware(
                        datetime.combine(date, check_in_time)
                    )

                    # Always create check-out (simulate completed workday)
                    # Check-out between 5:00 PM and 6:30 PM
                    check_out_hour = random.randint(17, 18)
                    check_out_minute = random.randint(0, 30) if check_out_hour == 17 else random.randint(0, 30)
                    check_out_time = time(check_out_hour, check_out_minute)

                    check_out_datetime = timezone.make_aware(
                        datetime.combine(date, check_out_time)
                    )

                    # Create attendance record
                    attendance, created = Attendance.objects.get_or_create(
                        employee=employee,
                        date=date,
                        defaults={
                            'check_in': check_in_datetime,
                            'check_out': check_out_datetime,
                        }
                    )

                    if created:
                        # Add some break records (1-3 breaks per day)
                        num_breaks = random.randint(1, 3)

                        for break_num in range(num_breaks):
                            # Break times during work hours
                            work_start = check_in_datetime
                            work_end = check_out_datetime

                            # Generate break start time (lunch break around 12-1 PM, others random)
                            if break_num == 0:  # Lunch break
                                break_start_hour = 12
                                break_start_minute = random.randint(0, 30)
                            else:
                                break_start_hour = random.randint(work_start.hour + 1, work_end.hour - 2)
                                break_start_minute = random.randint(0, 59)

                            break_start_time = time(break_start_hour, break_start_minute)
                            break_start_datetime = timezone.make_aware(
                                datetime.combine(date, break_start_time)
                            )

                            # Break duration (15-60 minutes)
                            break_duration_minutes = random.randint(15, 60)
                            break_end_datetime = break_start_datetime + timedelta(minutes=break_duration_minutes)

                            # Make sure break ends before work ends
                            if break_end_datetime < work_end:
                                Break.objects.create(
                                    attendance=attendance,
                                    break_in=break_start_datetime,
                                    break_out=break_end_datetime,
                                )

                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Created attendance for {employee.user.first_name} {employee.user.last_name} on {date}'
                            )
                        )

        self.stdout.write(self.style.SUCCESS('Sample data population completed!'))
        self.stdout.write(f'Check the monthly reports for employees to see the data.')
