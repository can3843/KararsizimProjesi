from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

User = get_user_model()


class UserModelTests(TestCase):
    def test_username_is_unique_case_insensitively_at_db_level(self):
        User.objects.create_user("KullaniciAdi", "a@example.com", "parola-12345")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("kullaniciadi", "b@example.com", "parola-12345")

    def test_email_is_lowercased_on_save(self):
        user = User.objects.create_user("zeynep", "Zeynep@Example.COM", "parola-12345")
        self.assertEqual(user.email, "zeynep@example.com")
