from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from polls.models import Poll, Report, Vote
from polls.tests import PASSWORD, make_poll

from . import limits, services
from .models import RateLimitHit

User = get_user_model()

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class ClientIpTests(TestCase):
    def ip(self, **meta):
        return services.client_ip(RequestFactory().get("/", **meta))

    def test_local_uses_remote_addr_and_ignores_forwarded_header(self):
        self.assertEqual(self.ip(REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4"), "10.0.0.5")

    @override_settings(SECURE_DEPLOYMENT=True)
    def test_vercel_uses_vercel_forwarded_for(self):
        self.assertEqual(
            self.ip(REMOTE_ADDR="10.0.0.5", HTTP_X_VERCEL_FORWARDED_FOR="203.0.113.7, 10.1.1.1"), "203.0.113.7"
        )

    def test_ipv6_addresses_in_the_same_64_block_are_one_client(self):
        first = self.ip(REMOTE_ADDR="2001:db8:1:2:aaaa:bbbb:cccc:dddd")
        second = self.ip(REMOTE_ADDR="2001:db8:1:2:1111:2222:3333:4444")
        self.assertEqual(first, second)


class RateLimitServiceTests(TestCase):
    limit = limits.Limit("test", 2, timedelta(minutes=10))

    def test_limit_applies_after_count_hits_and_not_to_other_identifiers(self):
        services.record(self.limit, "a")
        self.assertFalse(services.is_limited(self.limit, "a"))
        services.record(self.limit, "a")
        self.assertTrue(services.is_limited(self.limit, "a"))
        self.assertFalse(services.is_limited(self.limit, "b"))

    def test_hits_outside_the_window_do_not_count(self):
        services.record(self.limit, "a")
        services.record(self.limit, "a")
        RateLimitHit.objects.update(created_at=timezone.now() - timedelta(minutes=11))
        self.assertFalse(services.is_limited(self.limit, "a"))

    def test_scope_stores_a_salted_hash_not_the_raw_identifier(self):
        services.record(self.limit, "203.0.113.7")
        self.assertNotIn("203.0.113.7", RateLimitHit.objects.get().scope)

    def test_cleanup_removes_old_hits_and_expired_sessions(self):
        services.record(self.limit, "a")
        RateLimitHit.objects.update(created_at=timezone.now() - timedelta(days=3))
        services.record(self.limit, "b")
        session = self.client.session
        session["x"] = 1
        session.save()
        Session.objects.update(expire_date=timezone.now() - timedelta(days=1))
        services.cleanup()
        self.assertEqual(
            list(RateLimitHit.objects.values_list("scope", flat=True)), [services.make_scope(self.limit, "b")]
        )
        self.assertEqual(Session.objects.count(), 0)


class AnonymousVoteLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        cls.poll = make_poll(cls.author, counts=(0, 0))

    def vote(self, client=None, poll=None, **extra):
        poll = poll or self.poll
        return (client or Client()).post(
            reverse("polls:vote", args=[poll.public_id]), {"option_id": poll.options.first().pk}, **extra
        )

    def test_same_ip_cannot_stuff_one_poll_with_fresh_sessions(self):
        limit = limits.VOTE_POLL_IP.count
        statuses = [self.vote(**AJAX).status_code for _ in range(limit + 3)]
        self.assertEqual(statuses[:limit], [200] * limit)
        self.assertEqual(set(statuses[limit:]), {429})
        self.assertEqual(Vote.objects.count(), limit)
        self.assertEqual(Poll.objects.get(pk=self.poll.pk).total_votes, limit)

    def test_other_polls_are_not_blocked_by_the_per_poll_limit(self):
        for _ in range(limits.VOTE_POLL_IP.count):
            self.vote()
        other = make_poll(self.author, question="Başka bir anket sorusu burada", counts=(0, 0))
        self.assertEqual(self.vote(poll=other, **AJAX).status_code, 200)

    def test_attempt_limit_blocks_before_a_session_is_created(self):
        tight = limits.Limit("vote-try-ip", 2, timedelta(hours=1))
        with patch("polls.views.limits.VOTE_ATTEMPT_IP", tight):
            for _ in range(2):
                self.vote()
            sessions_before = Session.objects.count()
            response = self.vote(**AJAX)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(Session.objects.count(), sessions_before)
        self.assertIn("error", response.json())

    def test_limit_response_for_a_plain_form_post_is_a_429_page(self):
        for _ in range(limits.VOTE_POLL_IP.count):
            self.vote()
        response = self.vote()
        self.assertEqual(response.status_code, 429)
        self.assertTemplateUsed(response, "polls/detail.html")

    def test_logged_in_users_are_not_subject_to_the_anonymous_limits(self):
        for _ in range(limits.VOTE_POLL_IP.count):
            self.vote()
        voter = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        client = Client()
        client.force_login(voter)
        self.assertEqual(self.vote(client, **AJAX).status_code, 200)

    def test_different_ips_are_counted_separately(self):
        for _ in range(limits.VOTE_POLL_IP.count):
            self.vote()
        self.assertEqual(self.vote(Client(REMOTE_ADDR="198.51.100.9"), **AJAX).status_code, 200)


class LoginLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def attempt(self, username="ayse", password="yanlis-parola", client=None):
        return (client or self.client).post(reverse("accounts:login"), {"username": username, "password": password})

    def test_repeated_failures_for_one_username_lock_further_attempts(self):
        for _ in range(limits.LOGIN_USER.count):
            self.assertEqual(self.attempt().status_code, 200)
        response = self.attempt()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], str(int(limits.LOGIN_USER.window.total_seconds())))

    def test_correct_password_is_also_refused_while_locked(self):
        for _ in range(limits.LOGIN_USER.count):
            self.attempt()
        self.assertEqual(self.attempt(password=PASSWORD).status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_username_lock_is_case_insensitive(self):
        for _ in range(limits.LOGIN_USER.count):
            self.attempt(username="AYSE")
        self.assertEqual(self.attempt(username="ayse").status_code, 429)

    def test_lock_on_one_username_does_not_block_other_usernames(self):
        for _ in range(limits.LOGIN_USER.count):
            self.attempt()
        other = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        self.assertEqual(self.attempt(username=other.username, password=PASSWORD).status_code, 302)

    def test_one_ip_guessing_many_usernames_is_stopped_by_the_ip_limit(self):
        for index in range(limits.LOGIN_IP.count):
            self.attempt(username=f"kisi{index}")
        self.assertEqual(self.attempt(username="baskasi").status_code, 429)

    def test_successful_logins_do_not_consume_the_limit(self):
        for _ in range(limits.LOGIN_USER.count + 2):
            self.assertEqual(self.attempt(password=PASSWORD, client=Client()).status_code, 302)

    def test_get_requests_are_never_limited(self):
        for _ in range(limits.LOGIN_USER.count):
            self.attempt()
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)


class AdminLoginLimitTests(TestCase):
    def test_admin_login_failures_are_limited_per_ip(self):
        url = reverse("admin:login")
        for index in range(limits.ADMIN_LOGIN_IP.count):
            self.assertEqual(self.client.post(url, {"username": f"x{index}", "password": "y"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"username": "yeni", "password": "y"}).status_code, 429)
        self.assertEqual(self.client.get(url).status_code, 200)


class RegisterAndCreateLimitTests(TestCase):
    def register(self, index):
        return Client().post(reverse("accounts:register"), {
            "username": f"kisi{index}",
            "email": f"kisi{index}@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        })

    def test_one_ip_cannot_open_unlimited_accounts(self):
        for index in range(limits.REGISTER_IP.count):
            self.assertEqual(self.register(index).status_code, 302)
        response = self.register(99)
        self.assertEqual(response.status_code, 429)
        self.assertFalse(User.objects.filter(username="kisi99").exists())

    def test_poll_creation_is_limited_per_ip_even_across_accounts_and_deletions(self):
        data = {"question": "Bugün ne yapsam acaba?", "option": ["Bir", "İki"]}
        for index in range(limits.POLL_CREATE_IP.count):
            user = User.objects.create_user(f"yazar{index}", f"yazar{index}@example.com", PASSWORD)
            client = Client()
            client.force_login(user)
            self.assertEqual(client.post(reverse("polls:create"), data).status_code, 302)
            Poll.objects.all().delete()  # silmek sınırı sıfırlamamalı
        user = User.objects.create_user("sonyazar", "son@example.com", PASSWORD)
        client = Client()
        client.force_login(user)
        self.assertEqual(client.post(reverse("polls:create"), data).status_code, 429)
        self.assertEqual(Poll.objects.count(), 0)


class ReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        cls.reporter = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        cls.poll = make_poll(cls.author)

    def url(self):
        return reverse("polls:report", args=[self.poll.public_id])

    def login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_login_is_required(self):
        response = Client().post(self.url(), {"reason": "spam"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/giris/", response["Location"])
        self.assertEqual(Report.objects.count(), 0)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.login(self.reporter).get(self.url()).status_code, 405)

    def test_report_is_saved_and_redirects_back_to_the_poll(self):
        response = self.login(self.reporter).post(self.url(), {"reason": "spam"})
        self.assertRedirects(response, self.poll.get_absolute_url(), fetch_redirect_response=False)
        report = Report.objects.get()
        self.assertEqual((report.poll, report.reporter, report.reason), (self.poll, self.reporter, "spam"))

    def test_second_report_by_the_same_user_does_not_duplicate(self):
        client = self.login(self.reporter)
        client.post(self.url(), {"reason": "spam"})
        client.post(self.url(), {"reason": "other"})
        self.assertEqual(Report.objects.count(), 1)

    def test_invalid_reason_is_rejected(self):
        self.login(self.reporter).post(self.url(), {"reason": "bogus"})
        self.assertEqual(Report.objects.count(), 0)

    def test_owner_cannot_report_own_poll(self):
        self.login(self.author).post(self.url(), {"reason": "spam"})
        self.assertEqual(Report.objects.count(), 0)

    def test_unknown_poll_is_404(self):
        response = self.login(self.reporter).post(reverse("polls:report", args=["yok"]), {"reason": "spam"})
        self.assertEqual(response.status_code, 404)

    def test_reports_per_user_are_rate_limited(self):
        client = self.login(self.reporter)
        for index in range(limits.REPORT_USER.count + 1):
            poll = make_poll(self.author, question=f"Bildirilecek anket numara {index}")
            client.post(reverse("polls:report", args=[poll.public_id]), {"reason": "spam"})
        self.assertEqual(Report.objects.count(), limits.REPORT_USER.count)

    def test_report_form_is_shown_to_other_logged_in_users_only(self):
        detail = self.poll.get_absolute_url()
        self.assertContains(self.login(self.reporter).get(detail), "Bu anketi bildir")
        self.assertNotContains(self.login(self.author).get(detail), "Bu anketi bildir")
        self.assertNotContains(Client().get(detail), "Bu anketi bildir")

    def test_admin_lists_reports_and_can_close_selected_polls(self):
        admin = User.objects.create_superuser("yonetici", "yonetici@example.com", PASSWORD)
        self.login(self.reporter).post(self.url(), {"reason": "spam"})
        client = self.login(admin)
        self.assertEqual(client.get(reverse("admin:polls_poll_changelist")).status_code, 200)
        self.assertEqual(client.get(reverse("admin:polls_report_changelist")).status_code, 200)
        response = client.post(
            reverse("admin:polls_poll_changelist"),
            {"action": "close_selected", "_selected_action": [self.poll.pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Poll.objects.get(pk=self.poll.pk).status, Poll.Status.CLOSED)
