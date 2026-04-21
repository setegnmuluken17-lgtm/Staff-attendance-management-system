import base64
import binascii
import io
import json
import re
from datetime import datetime, time, timedelta
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path

import numpy as np
import openpyxl
from PIL import Image
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Attendance, Department, LeaveRequest, OfficeLocation, Organization, Shift, Staff

try:
    import face_recognition
except ImportError:  # pragma: no cover - depends on local environment
    face_recognition = None


OFFICE_LAT = getattr(settings, 'COMPANY_LATITUDE', 0.0)
OFFICE_LON = getattr(settings, 'COMPANY_LONGITUDE', 0.0)
MAX_DISTANCE = getattr(settings, 'ALLOWED_RADIUS_METERS', 100)
OFFICE_IP_PREFIX = getattr(settings, 'OFFICE_IP_PREFIX', '')
OFFICE_START_TIME = getattr(settings, 'OFFICE_START_TIME', time(8, 30))
FACE_STORE_PATH = Path(settings.BASE_DIR) / 'staff_face_encodings.json'
FACE_RECOGNITION_REQUIRED = getattr(settings, 'FACE_RECOGNITION_REQUIRED', False)
FACE_IMAGE_MAX_BYTES = getattr(settings, 'FACE_IMAGE_MAX_BYTES', 3 * 1024 * 1024)
ALLOWED_FACE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
PHONE_RULES = {
    '+251': {
        'label': 'Ethiopia',
        'pattern': r'^9\d{8}$',
        'message': 'Enter valid number.',
    },
    '+254': {
        'label': 'Kenya',
        'pattern': r'^[17]\d{8}$',
        'message': 'Kenyan phone numbers must contain 9 digits and usually start with 1 or 7.',
    },
    '+255': {
        'label': 'Tanzania',
        'pattern': r'^[67]\d{8}$',
        'message': 'Tanzanian phone numbers must contain 9 digits and usually start with 6 or 7.',
    },
}

REGISTER_ORGANIZATION_CODE = 'BDU'
REGISTER_LOCATION_CODES = ('PEDA', 'POLY')


def _generate_staff_id(prefix='STF'):
    counter = Staff.objects.filter(staff_id__startswith=prefix).count() + 1
    return f"{prefix}{counter:04d}"


def _get_default_organization():
    return Organization.objects.filter(is_active=True).order_by('name').first()


def _get_default_office_location(organization=None):
    queryset = OfficeLocation.objects.filter(is_active=True)
    if organization:
        queryset = queryset.filter(organization=organization)
    return queryset.order_by('organization__name', 'name').first()


def _get_register_organizations():
    return Organization.objects.filter(
        is_active=True,
        code=REGISTER_ORGANIZATION_CODE,
    )


def _get_register_locations():
    return OfficeLocation.objects.filter(
        is_active=True,
        organization__code=REGISTER_ORGANIZATION_CODE,
        code__in=REGISTER_LOCATION_CODES,
    ).select_related('organization')


def _office_location_is_configured():
    return OFFICE_LAT is not None and OFFICE_LON is not None


def _minutes_since_midnight(dt_value):
    local_value = timezone.localtime(dt_value)
    return (local_value.hour * 60) + local_value.minute


def _get_default_shift():
    return Shift.objects.filter(code='MORNING').first()


def _scope_queryset_for_user(
    queryset,
    user,
    organization_field='organization',
    office_location_field='office_location',
):
    office_location = getattr(user, 'office_location', None)
    if office_location:
        return queryset.filter(**{office_location_field: office_location})

    organization = getattr(user, 'organization', None)
    if organization:
        return queryset.filter(**{organization_field: organization})

    return queryset


def _get_attendance_policy_for_staff(staff_member):
    office_location = getattr(staff_member, 'office_location', None)
    if office_location:
        return {
            'latitude': office_location.latitude,
            'longitude': office_location.longitude,
            'radius_meters': office_location.radius_meters or MAX_DISTANCE,
            'ip_prefix': office_location.ip_prefix or '',
            'display_name': office_location.name,
            'office_location': office_location,
        }

    return {
        'latitude': OFFICE_LAT,
        'longitude': OFFICE_LON,
        'radius_meters': MAX_DISTANCE,
        'ip_prefix': OFFICE_IP_PREFIX,
        'display_name': 'Main Office',
        'office_location': None,
    }


def _get_shift_deadline(shift):
    base_shift = shift or _get_default_shift()
    if not base_shift:
        return OFFICE_START_TIME

    shift_start = datetime.combine(timezone.localdate(), base_shift.start_time)
    deadline = shift_start + timedelta(minutes=base_shift.grace_minutes)
    return deadline.time()


def _send_notification_email(subject, message, recipient):
    if not recipient:
        return
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [recipient],
        fail_silently=True,
    )


def _face_recognition_ready():
    return face_recognition is not None


def _load_face_store():
    if not FACE_STORE_PATH.exists():
        return {}

    try:
        return json.loads(FACE_STORE_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_face_store(data):
    FACE_STORE_PATH.write_text(json.dumps(data), encoding='utf-8')


def _get_face_encoding(staff_member):
    store = _load_face_store()
    return store.get(str(staff_member.pk))


def _set_face_encoding(staff_member, encoding):
    store = _load_face_store()
    store[str(staff_member.pk)] = encoding
    _save_face_store(store)


def _extract_face_encoding_from_data_url(data_url):
    if not _face_recognition_ready():
        raise ValueError('Face recognition is not available on this server yet.')

    if not data_url or ',' not in data_url:
        raise ValueError('Face image capture is required.')

    try:
        header, encoded_data = data_url.split(',', 1)
    except (ValueError, TypeError):
        raise ValueError('Invalid face image data.')

    if not header.startswith('data:') or ';base64' not in header:
        raise ValueError('Invalid face image format.')

    mime_type = header[5:].split(';', 1)[0].lower()
    if mime_type not in ALLOWED_FACE_MIME_TYPES:
        raise ValueError('Only JPEG, PNG, or WEBP face images are allowed.')

    try:
        image_bytes = base64.b64decode(encoded_data, validate=True)
    except (ValueError, TypeError, binascii.Error):
        raise ValueError('Invalid face image data.')

    if not image_bytes:
        raise ValueError('Face image capture is required.')
    if len(image_bytes) > FACE_IMAGE_MAX_BYTES:
        raise ValueError('Face image is too large. Please use a smaller capture.')

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.verify()
        image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    except (OSError, ValueError):
        raise ValueError('Uploaded face image is not a valid image file.')

    if image.width < 320 or image.height < 240:
        raise ValueError('Face image is too small. Move closer to the camera and try again.')

    image_array = np.array(image)
    brightness = float(image_array.mean())
    contrast = float(image_array.std())
    if brightness < 25 or brightness > 245:
        raise ValueError('Lighting is not suitable for face verification. Adjust the light and try again.')
    if contrast < 10:
        raise ValueError('Face image is too flat or blurry. Capture a clearer photo and try again.')

    face_locations = face_recognition.face_locations(image_array, model='hog')
    if len(face_locations) != 1:
        raise ValueError('Exactly one clear face must be visible in the camera.')

    encodings = face_recognition.face_encodings(image_array, known_face_locations=face_locations)
    if not encodings:
        raise ValueError('Face features could not be extracted. Try another capture.')

    return encodings[0].tolist()


def _validate_phone_number(country_code, phone_number):
    normalized_phone = re.sub(r'\D', '', phone_number or '')
    if not normalized_phone:
        raise ValueError('Phone number is required.')

    rule = PHONE_RULES.get(country_code)
    if rule and not re.fullmatch(rule['pattern'], normalized_phone):
        raise ValueError(rule['message'])

    if not rule and not re.fullmatch(r'^\d{6,15}$', normalized_phone):
        raise ValueError('Phone number must contain only digits and be between 6 and 15 digits long.')

    return normalized_phone


def _validate_registration_email(email):
    normalized_email = (email or '').strip().lower()
    if not normalized_email:
        raise ValueError('Email address is required.')

    try:
        validate_email(normalized_email)
    except ValidationError:
        raise ValueError('Enter a valid email address.')

    if normalized_email.count('@') != 1:
        raise ValueError('Enter a valid email address.')

    local_part, domain_part = normalized_email.split('@', 1)
    if len(local_part) < 2:
        raise ValueError('Email address is too short before the @ sign.')
    if '.' not in domain_part or domain_part.startswith('.') or domain_part.endswith('.'):
        raise ValueError('Email domain must include a valid dot-separated domain like example.com.')

    return normalized_email


def home(request):
    today = timezone.localdate()

    staff_qs = Staff.objects.filter(role='STAFF', is_approved=True)
    attendance_qs = Attendance.objects.filter(date=today, check_in__isnull=False)
    if request.user.is_authenticated:
        staff_qs = _scope_queryset_for_user(staff_qs, request.user)
        attendance_qs = _scope_queryset_for_user(attendance_qs, request.user)

    total_staff = staff_qs.count()
    today_attendance = attendance_qs.count()
    late_count = attendance_qs.filter(status='Late').count()

    context = {
        'total_staff': total_staff,
        'today_attendance': today_attendance,
        'late_count': late_count,
    }

    return render(request, 'home.html', context)


def export_excel(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Records"

    ws.append(["Name", "Staff ID", "Date", "Check In", "Check Out", "Status", "Method", "Location"])

    for record in Attendance.objects.select_related('staff').all():
        ws.append([
            record.staff.full_name,
            record.staff.staff_id,
            record.date.strftime("%Y-%m-%d"),
            record.check_in.strftime("%Y-%m-%d %H:%M:%S") if record.check_in else "",
            record.check_out.strftime("%Y-%m-%d %H:%M:%S") if record.check_out else "",
            record.status,
            record.method,
            record.location,
        ])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=attendance.xlsx'

    wb.save(response)
    return response


def export_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="attendance.pdf"'

    doc = SimpleDocTemplate(response)
    data = [
        ["Name", "Staff ID", "Date", "Check In", "Check Out", "Status", "Method"]
    ]

    for record in Attendance.objects.select_related('staff').all():
        data.append([
            record.staff.full_name,
            record.staff.staff_id,
            record.date.strftime("%Y-%m-%d"),
            record.check_in.strftime("%H:%M:%S") if record.check_in else "",
            record.check_out.strftime("%H:%M:%S") if record.check_out else "",
            record.status,
            record.method,
        ])

    table = Table(data, repeatRows=1)
    table.setStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ])

    doc.build([table])
    return response


def login_view(request):
    if request.user.is_authenticated:
        next_view = 'admin_page' if request.user.role == 'ADMIN' else 'dashboard'
        return redirect(next_view)

    error = None

    if request.method == 'POST':
        staff_id = request.POST.get('staff_id', '').strip().upper()
        password = request.POST.get('password', '')

        user = authenticate(request, staff_id=staff_id, password=password)
        if not user:
            error = 'Invalid staff ID or password.'
        elif not user.is_active or not user.is_approved:
            error = 'Account pending approval. Please wait for admin confirmation.'
        else:
            auth_login(request, user)
            return redirect('admin_page' if user.role == 'ADMIN' else 'dashboard')

    return render(request, 'login.html', {'error': error})


def admin_login(request):
    if request.user.is_authenticated:
        return redirect('admin_page' if request.user.role == 'ADMIN' else 'dashboard')

    error = None

    if request.method == 'POST':
        staff_id = request.POST.get('staff_id', '').strip().upper()
        password = request.POST.get('password', '')

        user = authenticate(request, staff_id=staff_id, password=password)
        if not user or user.role != 'ADMIN':
            error = 'Invalid admin ID or password.'
        elif not user.is_active or not user.is_approved:
            error = 'Account pending approval or inactive.'
        else:
            auth_login(request, user)
            return redirect('admin_page')

    return render(request, 'admin_login.html', {'error': error})


def register(request):
    error = None
    normalized_email = ''
    normalized_phone = ''

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        department_name = request.POST.get('department', '').strip()
        country_code = request.POST.get('country_code', '+251')
        phone_number = request.POST.get('phone_number', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('password_confirm', '')
        face_image_data = request.POST.get('face_image_data', '')
        if not full_name or not phone_number or not email or not password:
            error = 'Please complete all required fields.'
        elif password != confirm_password:
            error = 'Passwords do not match.'
        else:
            try:
                normalized_email = _validate_registration_email(email)
            except ValueError as exc:
                error = str(exc)

        if not error and Staff.objects.filter(email=normalized_email).exists():
            error = 'Email already registered.'

        if not error:
            try:
                normalized_phone = _validate_phone_number(country_code, phone_number)
            except ValueError as exc:
                error = str(exc)

        if not error:
            face_encoding = None
            if face_image_data:
                try:
                    face_encoding = _extract_face_encoding_from_data_url(face_image_data)
                except ValueError as exc:
                    error = str(exc)
            elif FACE_RECOGNITION_REQUIRED:
                error = 'Face capture is required for registration.'

            if not error:
                organization = None
                selected_organization_id = request.POST.get('organization_id')
                selected_location_id = request.POST.get('office_location_id')

                if selected_organization_id:
                    organization = Organization.objects.filter(
                        pk=selected_organization_id,
                        is_active=True,
                        code=REGISTER_ORGANIZATION_CODE,
                    ).first()
                organization = organization or _get_register_organizations().first() or _get_default_organization()

                office_location = None
                if selected_location_id:
                    office_location = OfficeLocation.objects.filter(
                        pk=selected_location_id,
                        is_active=True,
                        organization__code=REGISTER_ORGANIZATION_CODE,
                        code__in=REGISTER_LOCATION_CODES,
                    ).first()
                if office_location and organization and office_location.organization_id != organization.id:
                    error = 'Selected location does not belong to the selected organization.'
                elif not office_location:
                    error = 'Please select either Peda Campus or Poly Campus.'

            if not error:
                department = None
                if department_name:
                    department, _ = Department.objects.get_or_create(
                        organization=organization,
                        name=department_name.title(),
                    )
                default_shift = _get_default_shift()
                pending_id = _generate_staff_id(prefix='PENDING')
                staff_member = Staff.objects.create_user(
                    username=pending_id,
                    password=password,
                    full_name=full_name.title(),
                    phone_number=f"{country_code}{normalized_phone}",
                    organization=organization,
                    office_location=office_location,
                    department=department,
                    shift=default_shift,
                    email=normalized_email,
                    staff_id=pending_id,
                    role='STAFF',
                    is_approved=False,
                    is_active=False,
                )
                if face_encoding:
                    _set_face_encoding(staff_member, face_encoding)

                messages.success(
                    request,
                    'Registration submitted. An admin will approve and assign a staff ID shortly.',
                )
                return redirect('login')

    return render(
        request,
        'register.html',
        {
            'error': error,
            'face_recognition_ready': _face_recognition_ready(),
            'face_recognition_required': FACE_RECOGNITION_REQUIRED,
            'phone_rules_json': json.dumps(PHONE_RULES),
            'organizations': _get_register_organizations(),
            'office_locations': _get_register_locations(),
        },
    )


def logout_view(request):
    auth_logout(request)
    return render(request, 'logout.html')


@login_required(login_url='login')
def dashboard(request):
    if request.user.role != 'STAFF':
        return redirect('admin_page')

    attendance_records = Attendance.objects.filter(staff=request.user).order_by('-date')
    leave_requests = LeaveRequest.objects.filter(staff=request.user)
    today_record = attendance_records.filter(date=timezone.localdate()).first()
    if not today_record or not today_record.check_in:
        next_action = 'Check In'
    elif not today_record.check_out:
        next_action = 'Check Out'
    else:
        next_action = 'Completed'
    return render(
        request,
        'dashboard.html',
        {
            'staff_member': request.user,
            'attendance_records': attendance_records,
            'next_action': next_action,
            'allowed_radius': _get_attendance_policy_for_staff(request.user)['radius_meters'],
            'assigned_shift': request.user.shift or _get_default_shift(),
            'leave_requests': leave_requests,
            'face_enrolled': bool(_get_face_encoding(request.user)),
            'face_recognition_ready': _face_recognition_ready(),
            'face_recognition_required': FACE_RECOGNITION_REQUIRED,
            'organization': request.user.organization,
            'office_location': request.user.office_location,
        },
    )


@login_required(login_url='login')
def admin_page(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard')

    today = timezone.localdate()
    all_staff = _scope_queryset_for_user(
        Staff.objects.filter(role='STAFF', is_approved=True).select_related('organization', 'office_location', 'department'),
        request.user,
    )
    today_attendance = _scope_queryset_for_user(
        Attendance.objects.filter(date=today, check_in__isnull=False).select_related(
            'staff',
            'staff__department',
            'staff__organization',
            'staff__office_location',
            'organization',
            'office_location',
        ),
        request.user,
    )

    present_count = today_attendance.count()
    late_count = today_attendance.filter(status='Late').count()

    attended_ids = today_attendance.values_list('staff__staff_id', flat=True)
    absent_staff = all_staff.exclude(staff_id__in=attended_ids)

    current_month = today.month
    current_year = today.year
    monthly_attendance = _scope_queryset_for_user(
        Attendance.objects.filter(
        date__month=current_month,
        date__year=current_year,
        check_in__isnull=False,
        ).select_related('staff', 'staff__office_location', 'office_location'),
        request.user,
    )
    monthly_summary = monthly_attendance.values('staff__full_name', 'staff__staff_id').annotate(
        total_days=Count('id'),
    ).order_by('-total_days')

    days_elapsed = today.day
    total_possible_attendance = all_staff.count() * days_elapsed
    monthly_present_total = monthly_attendance.count()
    monthly_absent_total = max(total_possible_attendance - monthly_present_total, 0)
    monthly_attendance_rate = (
        round((monthly_present_total / total_possible_attendance) * 100, 1)
        if total_possible_attendance else 0
    )

    late_by_department = {}
    for record in today_attendance.filter(status='Late'):
        department_name = record.staff.department.name if record.staff.department else 'Unassigned'
        late_by_department[department_name] = late_by_department.get(department_name, 0) + 1

    punctual_map = {}
    for record in monthly_attendance:
        if not record.check_in:
            continue
        key = record.staff.staff_id
        punctual_map.setdefault(key, {
            'name': record.staff.full_name,
            'staff_id': record.staff.staff_id,
            'minutes': [],
        })
        punctual_map[key]['minutes'].append(_minutes_since_midnight(record.check_in))

    punctual_staff = []
    for entry in punctual_map.values():
        average_minutes = sum(entry['minutes']) / len(entry['minutes'])
        punctual_staff.append({
            'name': entry['name'],
            'staff_id': entry['staff_id'],
            'average_minutes': average_minutes,
            'display_time': f"{int(average_minutes // 60):02d}:{int(round(average_minutes % 60)):02d}",
        })

    punctual_staff.sort(key=lambda item: item['average_minutes'])
    punctual_staff = punctual_staff[:5]

    chart_data = {
        'present_absent': {
            'labels': ['Present', 'Absent'],
            'values': [present_count, absent_staff.count()],
        },
        'late_departments': {
            'labels': list(late_by_department.keys()) or ['No late staff'],
            'values': list(late_by_department.values()) or [0],
        },
        'monthly_rate': {
            'labels': ['Present', 'Missed'],
            'values': [monthly_present_total, monthly_absent_total],
            'rate': monthly_attendance_rate,
        },
        'punctual_staff': {
            'labels': [item['name'] for item in punctual_staff] or ['No data yet'],
            'values': [round(item['average_minutes'], 1) for item in punctual_staff] or [0],
        },
    }

    context = {
        'staff': all_staff,
        'pending_staff': _scope_queryset_for_user(
            Staff.objects.filter(is_approved=False).select_related('organization', 'office_location', 'department'),
            request.user,
        ),
        'shifts': Shift.objects.all(),
        'attendance': today_attendance,
        'pending_leave_requests': _scope_queryset_for_user(
            LeaveRequest.objects.filter(status='PENDING').select_related('staff', 'staff__organization'),
            request.user,
            organization_field='staff__organization',
            office_location_field='staff__office_location',
        ),
        'present_count': present_count,
        'late_count': late_count,
        'absent_staff': absent_staff,
        'absent_count': absent_staff.count(),
        'monthly_summary': monthly_summary,
        'monthly_attendance_rate': monthly_attendance_rate,
        'punctual_staff': punctual_staff,
        'chart_data_json': json.dumps(chart_data),
        'month': current_month,
        'today': today,
        'active_organization': request.user.organization,
        'active_office_location': request.user.office_location,
    }

    return render(request, 'admin_page.html', context)


@login_required(login_url='login')
def daily_report(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard')

    today = timezone.localdate()
    records = _scope_queryset_for_user(Attendance.objects.filter(date=today), request.user)

    context = {
        'records': records,
        'day': today,
    }
    return render(request, 'daily_report.html', context)


@login_required(login_url='login')
def monthly_report(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard')

    today = timezone.localdate()
    records = _scope_queryset_for_user(Attendance.objects.filter(
        date__month=today.month,
        date__year=today.year,
    ).select_related('staff'), request.user)

    summary = records.values('staff__full_name', 'staff__staff_id').annotate(
        days_present=Count('id'),
    ).order_by('-days_present')

    context = {
        'summary': summary,
        'month': today.month,
        'year': today.year,
    }
    return render(request, 'monthly_report.html', context)


@login_required(login_url='login')
def approve_staff(request, staff_pk):
    if request.user.role != 'ADMIN':
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('admin_page')

    staff_queryset = _scope_queryset_for_user(Staff.objects.all(), request.user)
    staff_member = get_object_or_404(staff_queryset, pk=staff_pk)
    role = request.POST.get('role', 'STAFF').upper()
    shift_id = request.POST.get('shift_id')
    assigned_shift = Shift.objects.filter(pk=shift_id).first() if shift_id else _get_default_shift()

    staff_id = _generate_staff_id(prefix='STF')
    staff_member.staff_id = staff_id
    staff_member.username = staff_id
    staff_member.role = role
    staff_member.shift = assigned_shift
    staff_member.is_approved = True
    staff_member.is_active = True
    staff_member.save()

    _send_notification_email(
        'SAMS account approved',
        (
            f"Hello {staff_member.full_name},\n\n"
            f"Your account has been approved.\n"
            f"Staff ID: {staff_id}\n"
            f"Role: {role}\n"
            f"Shift: {assigned_shift.name if assigned_shift else 'Default'}\n\n"
            f"You can now sign in to the attendance system."
        ),
        staff_member.email,
    )

    messages.success(
        request,
        f"{staff_member.full_name} approved as {role}. Staff ID assigned: {staff_id}",
    )

    return redirect('admin_page')


def calculate_distance(lat1, lon1, lat2, lon2):
    r = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


@login_required(login_url='login')
def attendance(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required.'}, status=405)

    staff_member = request.user

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid payload'}, status=400)

    latitude = payload.get('latitude')
    longitude = payload.get('longitude')
    face_image_data = payload.get('face_image_data')
    method_used = ''
    location_desc = ''
    registered_face_encoding = _get_face_encoding(staff_member)

    if registered_face_encoding:
        if not _face_recognition_ready():
            return JsonResponse({'error': 'Face recognition is not available on this server yet.'}, status=503)
        if not face_image_data:
            return JsonResponse({'error': 'Live face capture is required for this account.'}, status=400)

        try:
            live_face_encoding = _extract_face_encoding_from_data_url(face_image_data)
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        face_distance = face_recognition.face_distance(
            [np.array(registered_face_encoding)],
            np.array(live_face_encoding),
        )[0]
        face_match = face_recognition.compare_faces(
            [np.array(registered_face_encoding)],
            np.array(live_face_encoding),
            tolerance=0.45,
        )[0]
        if not face_match:
            return JsonResponse(
                {'error': f'Face verification failed. Match score {face_distance:.2f} is outside the allowed range.'},
                status=400,
            )
    elif FACE_RECOGNITION_REQUIRED:
        return JsonResponse({'error': 'No registered face found for this account. Please enroll a face first.'}, status=400)

    attendance_policy = _get_attendance_policy_for_staff(staff_member)
    policy_lat = attendance_policy['latitude']
    policy_lon = attendance_policy['longitude']
    policy_radius = attendance_policy['radius_meters']
    policy_ip_prefix = attendance_policy['ip_prefix']
    office_location = attendance_policy['office_location']

    user_ip = request.META.get('REMOTE_ADDR', '')
    if policy_ip_prefix and user_ip.startswith(policy_ip_prefix):
        method_used = 'WiFi'
        location_desc = f"{attendance_policy['display_name']} Wi-Fi"
    elif latitude is not None and longitude is not None:
        if policy_lat is None or policy_lon is None:
            return JsonResponse({
                'error': 'Office GPS location is not configured yet. Please contact the administrator.'
            }, status=400)
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Geolocation values must be numbers.'}, status=400)

        distance = calculate_distance(lat, lon, policy_lat, policy_lon)
        if distance > policy_radius:
            return JsonResponse({
                'error': f"You are {distance:.0f} meters from the office. Check-in is allowed only within {policy_radius} meters."
            }, status=400)
        method_used = 'GPS'
        location_desc = f"{lat:.6f},{lon:.6f}"
    else:
        return JsonResponse({
            'error': f'Current GPS location is required. Move within {policy_radius} meters of the office and allow location access.'
        }, status=400)

    today = timezone.localdate()
    now = timezone.localtime()

    try:
        with transaction.atomic():
            record = (
                Attendance.objects.select_for_update()
                .filter(staff=staff_member, date=today)
                .first()
            )
            if not record:
                try:
                    record = Attendance.objects.create(
                        staff=staff_member,
                        organization=staff_member.organization,
                        office_location=office_location,
                        date=today,
                        location=location_desc,
                    )
                except IntegrityError:
                    record = Attendance.objects.select_for_update().get(
                        staff=staff_member,
                        date=today,
                    )

            if not record.check_in:
                allowed_start_time = _get_shift_deadline(staff_member.shift)
                record.check_in = now
                record.method = method_used
                record.organization = staff_member.organization
                record.office_location = office_location
                record.location = location_desc
                record.is_late = now.time() > allowed_start_time
                record.status = 'Late' if record.is_late else 'Present'
                record.save(update_fields=['check_in', 'method', 'organization', 'office_location', 'location', 'is_late', 'status'])
                if record.is_late:
                    _send_notification_email(
                        'Late attendance alert',
                        (
                            f"Hello {staff_member.full_name},\n\n"
                            f"Your attendance for {today.strftime('%Y-%m-%d')} was marked late.\n"
                            f"Check-in time: {now.strftime('%H:%M')}\n"
                            f"Late cutoff for your shift: {allowed_start_time.strftime('%H:%M')}\n"
                            f"Shift: {staff_member.shift.name if staff_member.shift else 'Default'}"
                        ),
                        staff_member.email,
                    )
                return JsonResponse({
                    'status': f"Check-in recorded ({method_used}).",
                    'action': 'Check In',
                    'method': method_used,
                    'shift': staff_member.shift.name if staff_member.shift else None,
                    'late_cutoff': allowed_start_time.strftime('%H:%M'),
                })

            if not record.check_out:
                record.check_out = now
                record.save(update_fields=['check_out'])
                return JsonResponse({
                    'status': f"Check-out recorded ({method_used}).",
                    'action': 'Check Out',
                    'method': method_used,
                })

            return JsonResponse({
                'status': 'Attendance already marked for today.',
                'action': 'Completed',
                'method': record.method,
            })
    except IntegrityError:
        return JsonResponse({
            'error': 'Duplicate attendance request detected. Please refresh and try again.',
        }, status=409)


@login_required(login_url='login')
def submit_leave_request(request):
    if request.user.role != 'STAFF':
        return redirect('admin_page')

    if request.method != 'POST':
        return redirect('dashboard')

    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')
    reason = request.POST.get('reason', '').strip()

    if not start_date or not end_date or not reason:
        messages.error(request, 'Please complete all leave request fields.')
        return redirect('dashboard')

    LeaveRequest.objects.create(
        staff=request.user,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    messages.success(request, 'Leave request submitted successfully.')
    return redirect('dashboard')


@login_required(login_url='login')
def update_leave_request(request, leave_pk, status):
    if request.user.role != 'ADMIN':
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('admin_page')

    leave_queryset = _scope_queryset_for_user(
        LeaveRequest.objects.select_related('staff', 'staff__organization', 'staff__office_location'),
        request.user,
        organization_field='staff__organization',
        office_location_field='staff__office_location',
    )
    leave_request = get_object_or_404(leave_queryset, pk=leave_pk)
    if status not in {'APPROVED', 'REJECTED'}:
        return redirect('admin_page')

    leave_request.status = status
    leave_request.admin_comment = request.POST.get('admin_comment', '').strip()
    leave_request.save(update_fields=['status', 'admin_comment', 'updated_at'])

    _send_notification_email(
        f"Leave request {status.lower()}",
        (
            f"Hello {leave_request.staff.full_name},\n\n"
            f"Your leave request from {leave_request.start_date} to {leave_request.end_date} "
            f"has been {status.lower()}.\n"
            f"Reason: {leave_request.reason}\n"
            f"Admin comment: {leave_request.admin_comment or 'No comment provided.'}"
        ),
        leave_request.staff.email,
    )

    messages.success(request, f'Leave request {status.lower()} successfully.')
    return redirect('admin_page')
