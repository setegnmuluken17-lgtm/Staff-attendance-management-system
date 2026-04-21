from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_default_organization(apps, schema_editor):
    Organization = apps.get_model('staff', 'Organization')
    OfficeLocation = apps.get_model('staff', 'OfficeLocation')
    Department = apps.get_model('staff', 'Department')
    Staff = apps.get_model('staff', 'Staff')
    Attendance = apps.get_model('staff', 'Attendance')

    organization, _ = Organization.objects.get_or_create(
        code=getattr(settings, 'DEFAULT_ORGANIZATION_CODE', 'DEFAULT'),
        defaults={
            'name': getattr(settings, 'DEFAULT_ORGANIZATION_NAME', 'Default Organization'),
            'is_active': True,
        },
    )
    location, _ = OfficeLocation.objects.get_or_create(
        organization=organization,
        code=getattr(settings, 'DEFAULT_LOCATION_CODE', 'MAIN'),
        defaults={
            'name': getattr(settings, 'DEFAULT_LOCATION_NAME', 'Main Office'),
            'latitude': getattr(settings, 'COMPANY_LATITUDE', None),
            'longitude': getattr(settings, 'COMPANY_LONGITUDE', None),
            'radius_meters': getattr(settings, 'ALLOWED_RADIUS_METERS', 100),
            'ip_prefix': getattr(settings, 'OFFICE_IP_PREFIX', ''),
            'is_active': True,
        },
    )

    Department.objects.filter(organization__isnull=True).update(organization=organization)
    Staff.objects.filter(organization__isnull=True).update(organization=organization)
    Staff.objects.filter(office_location__isnull=True).update(office_location=location)
    Attendance.objects.filter(organization__isnull=True).update(organization=organization)
    Attendance.objects.filter(office_location__isnull=True).update(office_location=location)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('staff', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('code', models.CharField(max_length=30, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='OfficeLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('code', models.CharField(max_length=30)),
                ('latitude', models.FloatField(blank=True, null=True)),
                ('longitude', models.FloatField(blank=True, null=True)),
                ('radius_meters', models.PositiveIntegerField(default=100)),
                ('ip_prefix', models.CharField(blank=True, max_length=100)),
                ('is_active', models.BooleanField(default=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='locations', to='staff.organization')),
            ],
            options={
                'ordering': ['organization__name', 'name'],
                'unique_together': {('organization', 'code')},
            },
        ),
        migrations.AddField(
            model_name='department',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='departments', to='staff.organization'),
        ),
        migrations.AlterField(
            model_name='department',
            name='name',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterModelOptions(
            name='department',
            options={'ordering': ['name']},
        ),
        migrations.AlterUniqueTogether(
            name='department',
            unique_together={('organization', 'name')},
        ),
        migrations.AddField(
            model_name='staff',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='staff_members', to='staff.organization'),
        ),
        migrations.AddField(
            model_name='staff',
            name='office_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='staff_members', to='staff.officelocation'),
        ),
        migrations.AddField(
            model_name='attendance',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendances', to='staff.organization'),
        ),
        migrations.AddField(
            model_name='attendance',
            name='office_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendances', to='staff.officelocation'),
        ),
        migrations.RunPython(seed_default_organization, migrations.RunPython.noop),
    ]
