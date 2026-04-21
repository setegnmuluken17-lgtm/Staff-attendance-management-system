from django.contrib.auth.backends import ModelBackend

from .models import Staff


class StaffIDBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, staff_id=None, **kwargs):
        login_id = (staff_id or username or '').strip().upper()
        if not login_id or not password:
            return None

        try:
            user = Staff.objects.get(staff_id=login_id)
        except Staff.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
