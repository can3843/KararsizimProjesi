from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

PASSWORD = "gizli-sifre-2026"


class UserModelTests(TestCase):
    def test_username_is_unique_case_insensitively_at_db_level(self):
        User.objects.create_user("KullaniciAdi", "a@example.com", PASSWORD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("kullaniciadi", "b@example.com", PASSWORD)

    def test_email_is_lowercased_on_save(self):
        user = User.objects.create_user("zeynep", "Zeynep@Example.COM", PASSWORD)
        self.assertEqual(user.email, "zeynep@example.com")


class RegisterTests(TestCase):
    url = reverse("accounts:register")

    def register(self, **overrides):
        data = {
            "username": "ayse",
            "email": "ayse@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_register_logs_in_and_shows_welcome_toast(self):
        response = self.register()
        # Hedef sayfayı burada açmayız: mesaj ilk gösterimde tüketilir.
        self.assertRedirects(response, reverse("polls:index"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(User.objects.get(username="ayse").pk))
        page = self.client.get(reverse("polls:index"))
        self.assertContains(page, "Hoş geldin, @ayse")

    def test_register_page_renders(self):
        self.assertContains(self.client.get(self.url), "Kayıt ol")

    def test_duplicate_email_is_rejected(self):
        self.register()
        self.client.logout()
        response = self.register(username="mehmet", email="ayse@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "email", "Bu e-posta ile zaten bir hesap var.")
        self.assertContains(response, "Bu e-posta ile zaten bir hesap var.")
        self.assertFalse(User.objects.filter(username="mehmet").exists())

    def test_duplicate_email_differing_in_case_is_rejected(self):
        self.register()
        self.client.logout()
        response = self.register(username="mehmet", email="AYSE@Example.com")
        self.assertFormError(response.context["form"], "email", "Bu e-posta ile zaten bir hesap var.")

    def test_username_differing_only_in_case_is_rejected(self):
        self.register(username="KullaniciAdi", email="a@example.com")
        self.client.logout()
        response = self.register(username="kullaniciadi", email="b@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_username_characters_are_rejected(self):
        for username in ["ay se", "ayşe", "ayse!", "ab", "a" * 21]:
            with self.subTest(username=username):
                response = self.register(username=username)
                self.assertEqual(response.status_code, 200)
                self.assertIn("username", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)

    def test_forbidden_usernames_are_rejected(self):
        for username in ["admin", "Admin", "giris", "kayit"]:
            with self.subTest(username=username):
                response = self.register(username=username)
                self.assertFormError(response.context["form"], "username", "Bu kullanıcı adı kullanılamaz.")

    def test_email_is_required(self):
        response = self.register(email="")
        self.assertIn("email", response.context["form"].errors)

    def test_password_mismatch_is_reported_under_the_field(self):
        response = self.register(password2="baska-bir-parola-1")
        self.assertFormError(response.context["form"], "password2", "Parolalar eşleşmiyor.")

    def test_short_password_is_rejected(self):
        response = self.register(password1="kisa1", password2="kisa1")
        self.assertIn("password2", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)

    def test_authenticated_user_is_redirected_away(self):
        self.register()
        self.assertRedirects(self.client.get(self.url), reverse("polls:index"))


class LoginLogoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("KullaniciAdi", "kullanici@example.com", PASSWORD)

    def login(self, username="KullaniciAdi", password=PASSWORD, **extra):
        return self.client.post(reverse("accounts:login"), {"username": username, "password": password, **extra})

    def test_login_works(self):
        self.assertRedirects(self.login(), reverse("polls:index"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_is_case_insensitive_for_username(self):
        self.assertRedirects(self.login(username="kullaniciadi"), reverse("polls:index"))
        page = self.client.get(reverse("polls:index"))
        self.assertContains(page, "@KullaniciAdi")

    def test_wrong_password_shows_turkish_error(self):
        response = self.login(password="yanlis-parola")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kullanıcı adı veya parola hatalı.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_next_is_honoured(self):
        response = self.login(next="/anket/olustur/")
        self.assertRedirects(response, "/anket/olustur/", fetch_redirect_response=False)

    def test_external_next_is_ignored(self):
        response = self.login(next="https://example.org/")
        self.assertRedirects(response, reverse("polls:index"))

    def test_login_notice_is_shown_when_coming_from_create_page(self):
        response = self.client.get(reverse("accounts:login") + "?next=/anket/olustur/")
        self.assertContains(response, "Anket oluşturmak için giriş yapman gerekiyor")

    def test_login_notice_is_hidden_otherwise(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(response, "Anket oluşturmak için giriş yapman gerekiyor")

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_via_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("polls:index"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_page_redirects_authenticated_user(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse("accounts:login")), reverse("polls:index"))


class HeaderAndPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ayse", "gizli.adres@example.com", PASSWORD)

    def test_anonymous_header(self):
        page = self.client.get(reverse("polls:index"))
        self.assertContains(page, "Giriş yap")
        self.assertContains(page, "Kayıt ol")
        self.assertNotContains(page, "Çıkış yap")

    def test_authenticated_header_shows_username_and_create_link(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("polls:index"))
        self.assertContains(page, "@ayse")
        self.assertContains(page, "Anket oluştur")
        self.assertContains(page, "Çıkış yap")
        self.assertNotContains(page, "Giriş yap")

    def test_email_is_never_rendered(self):
        self.client.force_login(self.user)
        for url in [reverse("polls:index"), reverse("accounts:register"), reverse("accounts:login")]:
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url, follow=True), "gizli.adres@example.com")

    def test_email_is_not_rendered_after_registering(self):
        self.client.post(reverse("accounts:register"), {
            "username": "yeni", "email": "yeni.adres@example.com",
            "password1": PASSWORD, "password2": PASSWORD,
        })
        page = self.client.get(reverse("polls:index"))
        self.assertContains(page, "@yeni")
        self.assertNotContains(page, "yeni.adres@example.com")
