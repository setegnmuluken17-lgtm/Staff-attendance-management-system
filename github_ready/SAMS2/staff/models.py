from datetime import time

from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=30, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name or "Unknown Organization"


class OfficeLocation(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='locations',
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    radius_meters = models.PositiveIntegerField(default=100)
    ip_prefix = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['organization__name', 'name']
        unique_together = ('organization', 'code')

    def __str__(self):
        return f"{self.organization.name} - {self.name}"


class Department(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='departments',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name or "Unknown"


class Shift(models.Model):
    SHIFT_CHOICES = (
        ('MORNING', 'Morning'),
        ('NIGHT', 'Night'),
        ('FLEX', 'Flexible'),
    )

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, choices=SHIFT_CHOICES)
    start_time = models.TimeField(default=time(8, 30))
    grace_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['start_time', 'name']

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')})"


class Staff(AbstractUser):
    first_name = None
    last_name = None

    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('HR', 'HR'),
        ('STAFF', 'Staff'),
    )

    staff_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    #department = models.ForeignKey(Department, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
    )
    office_location = models.ForeignKey(
        OfficeLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    shift = models.ForeignKey(
        Shift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='STAFF')
    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return self.full_name or self.username


class Attendance(models.Model):
    STATUS_CHOICES = (
        ('Present', 'Present'),
        ('Late', 'Late'),
        ('Absent', 'Absent'),
    )

    METHOD_CHOICES = (
        ('GPS', 'GPS'),
        ('WiFi', 'Office Wi-Fi'),
    )

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='attendances',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendances',
    )
    office_location = models.ForeignKey(
        OfficeLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendances',
    )
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Present')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, blank=True)
    location = models.CharField(max_length=255, blank=True)
    is_late = models.BooleanField(default=False)

    class Meta:
        unique_together = ('staff', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.staff.full_name} - {self.date}"


class LeaveRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    )

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='leave_requests',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_comment = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.staff.full_name} leave {self.start_date} to {self.end_date}"
