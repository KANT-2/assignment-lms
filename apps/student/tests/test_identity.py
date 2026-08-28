from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.student.identity import external_student_id


class StudentIdentityTests(SimpleTestCase):
    @override_settings(DEV_SKIP_AUTH=True)
    def test_dev_student_uses_kim_student_id(self):
        request = SimpleNamespace(user=SimpleNamespace(id=999))

        self.assertEqual(external_student_id(request), 11)

    @override_settings(DEV_SKIP_AUTH=False)
    def test_real_login_uses_authenticated_user_id(self):
        request = SimpleNamespace(user=SimpleNamespace(id=42))

        self.assertEqual(external_student_id(request), 42)
