from datetime import time

from django.apps import AppConfig, apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate


class StaffConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'staff'

    def ready(self):
        post_migrate.connect(_ensure_default_admin, sender=self)


def _ensure_default_admin(sender, **kwargs):
    Staff = get_user_model()
    Organization = django_apps.get_model('staff', 'Organization')
    OfficeLocation = django_apps.get_model('staff', 'OfficeLocation')
    Department = django_apps.get_model('staff', 'Department')
    Shift = django_apps.get_model('staff', 'Shift')

    staff_id = getattr(settings, 'DEFAULT_ADMIN_STAFF_ID', 'ADM0001').upper()
    password = getattr(settings, 'DEFAULT_ADMIN_PASSWORD', '2127')
    full_name = getattr(settings, 'DEFAULT_ADMIN_FULL_NAME', 'System Admin')
    email = getattr(settings, 'DEFAULT_ADMIN_EMAIL', 'admin@sams.local')
    department_name = getattr(settings, 'DEFAULT_ADMIN_DEPARTMENT', 'Administration')
    organization_name = getattr(settings, 'DEFAULT_ORGANIZATION_NAME', 'Default Organization')
    organization_code = getattr(settings, 'DEFAULT_ORGANIZATION_CODE', 'DEFAULT')
    location_name = getattr(settings, 'DEFAULT_LOCATION_NAME', 'Main Office')
    location_code = getattr(settings, 'DEFAULT_LOCATION_CODE', 'MAIN')
    peda_admin_staff_id = getattr(settings, 'PEDA_ADMIN_STAFF_ID', 'BDU0001').upper()
    peda_admin_password = getattr(settings, 'PEDA_ADMIN_PASSWORD', password)
    peda_admin_full_name = getattr(settings, 'PEDA_ADMIN_FULL_NAME', 'Peda Campus Admin')
    peda_admin_email = getattr(settings, 'PEDA_ADMIN_EMAIL', 'peda.admin@sams.local')
    poly_admin_staff_id = getattr(settings, 'POLY_ADMIN_STAFF_ID', 'BIT0001').upper()
    poly_admin_password = getattr(settings, 'POLY_ADMIN_PASSWORD', password)
    poly_admin_full_name = getattr(settings, 'POLY_ADMIN_FULL_NAME', 'Poly Campus Admin')
    poly_admin_email = getattr(settings, 'POLY_ADMIN_EMAIL', 'poly.admin@sams.local')

    organization, _ = Organization.objects.get_or_create(
        code=organization_code,
        defaults={'name': organization_name},
    )
    location_defaults = {
        'name': location_name,
        'latitude': getattr(settings, 'COMPANY_LATITUDE', None),
        'longitude': getattr(settings, 'COMPANY_LONGITUDE', None),
        'radius_meters': getattr(settings, 'ALLOWED_RADIUS_METERS', 100),
        'ip_prefix': getattr(settings, 'OFFICE_IP_PREFIX', ''),
    }
    office_location, _ = OfficeLocation.objects.get_or_create(
        organization=organization,
        code=location_code,
        defaults=location_defaults,
    )
    OfficeLocation.objects.get_or_create(
        organization=organization,
        code='PEDA',
        defaults={
            'name': 'Peda Campus',
            'latitude': getattr(settings, 'PEDA_CAMPUS_LATITUDE', None),
            'longitude': getattr(settings, 'PEDA_CAMPUS_LONGITUDE', None),
            'radius_meters': getattr(settings, 'PEDA_CAMPUS_RADIUS_METERS', getattr(settings, 'ALLOWED_RADIUS_METERS', 100)),
            'ip_prefix': getattr(settings, 'PEDA_CAMPUS_IP_PREFIX', ''),
        },
    )
    peda_location = OfficeLocation.objects.get(
        organization=organization,
        code='PEDA',
    )
    OfficeLocation.objects.get_or_create(
        organization=organization,
        code='POLY',
        defaults={
            'name': 'Poly Campus',
            'latitude': getattr(settings, 'POLY_CAMPUS_LATITUDE', None),
            'longitude': getattr(settings, 'POLY_CAMPUS_LONGITUDE', None),
            'radius_meters': getattr(settings, 'POLY_CAMPUS_RADIUS_METERS', getattr(settings, 'ALLOWED_RADIUS_METERS', 100)),
            'ip_prefix': getattr(settings, 'POLY_CAMPUS_IP_PREFIX', ''),
        },
    )
    poly_location = OfficeLocation.objects.get(
        organization=organization,
        code='POLY',
    )
    department, _ = Department.objects.get_or_create(
        organization=organization,
        name=department_name,
    )
    default_shift, _ = Shift.objects.get_or_create(
        code='MORNING',
        defaults={
            'name': 'Morning Shift',
            'start_time': time(8, 30),
            'grace_minutes': 10,
        },
    )
    Shift.objects.get_or_create(
        code='NIGHT',
        defaults={
            'name': 'Night Shift',
            'start_time': time(20, 0),
            'grace_minutes': 10,
        },
    )
    Shift.objects.get_or_create(
        code='FLEX',
        defaults={
            'name': 'Flexible Shift',
            'start_time': time(9, 30),
            'grace_minutes': 20,
        },
    )

    admin_user, created = Staff.objects.get_or_create(
        staff_id=staff_id,
        defaults={
            'username': staff_id,
            'full_name': full_name,
            'email': email,
            'role': 'ADMIN',
            'is_staff': True,
            'is_superuser': True,
            'is_approved': True,
            'is_active': True,
            'organization': organization,
            'office_location': office_location,
            'department': department,
            'shift': default_shift,
        },
    )

    if created:
        admin_user.set_password(password)
        admin_user.save(update_fields=['password'])
    else:
        updates = []
        if admin_user.organization_id != organization.id:
            admin_user.organization = organization
            updates.append('organization')
        if admin_user.office_location_id != office_location.id:
            admin_user.office_location = office_location
            updates.append('office_location')
        if admin_user.department_id != department.id:
            admin_user.department = department
            updates.append('department')
        if updates:
            admin_user.save(update_fields=updates)

    for campus_admin in (
        {
            'staff_id': peda_admin_staff_id,
            'password': peda_admin_password,
            'full_name': peda_admin_full_name,
            'email': peda_admin_email,
            'office_location': peda_location,
        },
        {
            'staff_id': poly_admin_staff_id,
            'password': poly_admin_password,
            'full_name': poly_admin_full_name,
            'email': poly_admin_email,
            'office_location': poly_location,
        },
    ):
        campus_admin_user, created = Staff.objects.get_or_create(
            staff_id=campus_admin['staff_id'],
            defaults={
                'username': campus_admin['staff_id'],
                'full_name': campus_admin['full_name'],
                'email': campus_admin['email'],
                'role': 'ADMIN',
                'is_staff': True,
                'is_superuser': False,
                'is_approved': True,
                'is_active': True,
                'organization': organization,
                'office_location': campus_admin['office_location'],
                'department': department,
                'shift': default_shift,
            },
        )

        if created:
            campus_admin_user.set_password(campus_admin['password'])
            campus_admin_user.save(update_fields=['password'])
        else:
            updates = []
            if campus_admin_user.organization_id != organization.id:
                campus_admin_user.organization = organization
                updates.append('organization')
            if campus_admin_user.office_location_id != campus_admin['office_location'].id:
                campus_admin_user.office_location = campus_admin['office_location']
                updates.append('office_location')
            if campus_admin_user.department_id != department.id:
                campus_admin_user.department = department
                updates.append('department')
            if campus_admin_user.shift_id != default_shift.id:
                campus_admin_user.shift = default_shift
                updates.append('shift')
            if campus_admin_user.role != 'ADMIN':
                campus_admin_user.role = 'ADMIN'
                updates.append('role')
            if not campus_admin_user.is_staff:
                campus_admin_user.is_staff = True
                updates.append('is_staff')
            if not campus_admin_user.is_approved:
                campus_admin_user.is_approved = True
                updates.append('is_approved')
            if not campus_admin_user.is_active:
                campus_admin_user.is_active = True
                updates.append('is_active')
            if updates:
                campus_admin_user.save(update_fields=updates)
