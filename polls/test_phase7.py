from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Poll
from .tests import LONG_QUESTION, PASSWORD, make_poll

User = get_user_model()


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        make_poll(cls.author, question="Hafta sonu sinemaya gidelim mi?")
        make_poll(cls.author, question="Akşam yemeği için ne sipariş edelim?")
        make_poll(cls.author, question="Yüzde 100 emin misin kararından?")

    def search(self, query, **extra):
        return self.client.get(reverse("polls:index"), {"q": query, **extra})

    def questions(self, response):
        return [poll.question for poll in response.context["polls"]]

    def test_matches_part_of_the_question_case_insensitively(self):
        self.assertEqual(self.questions(self.search("SiNEMA")), ["Hafta sonu sinemaya gidelim mi?"])

    def test_no_match_shows_empty_state_with_the_query(self):
        response = self.search("yokböyleşey")
        self.assertEqual(self.questions(response), [])
        self.assertContains(response, "için anket bulunamadı.")
        self.assertContains(response, "Aramayı temizle")

    def test_blank_query_lists_everything(self):
        self.assertEqual(len(self.questions(self.search("   "))), 3)

    def test_percent_and_underscore_are_literal_characters(self):
        self.assertEqual(self.questions(self.search("%")), [])
        self.assertEqual(self.questions(self.search("_")), [])

    def test_query_is_html_escaped(self):
        response = self.search("<script>alert(1)</script>")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_tabs_and_load_more_keep_the_query(self):
        response = self.search("sinema", tab="populer")
        self.assertContains(response, 'href="?tab=yeni&amp;q=sinema"')
        self.assertContains(response, 'name="q" value="sinema"')

    def test_overlong_query_is_truncated_not_an_error(self):
        self.assertEqual(self.search("a" * 5000).status_code, 200)

    def test_search_applies_within_the_closed_tab(self):
        make_poll(self.author, question="Kapanmış sinema anketi burada", status=Poll.Status.CLOSED)
        response = self.search("sinema", tab="kapananlar")
        self.assertEqual(self.questions(response), ["Kapanmış sinema anketi burada"])


class DurationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def setUp(self):
        self.client.force_login(self.user)

    def create(self, **extra):
        return self.client.post(
            reverse("polls:create"), {"question": LONG_QUESTION, "option": ["Sinema", "Restoran"], **extra}
        )

    def test_default_is_open_ended(self):
        self.create()
        self.assertIsNone(Poll.objects.get().closes_at)

    def test_chosen_duration_sets_closes_at(self):
        before = timezone.now()
        self.create(duration="1d")
        closes_at = Poll.objects.get().closes_at
        self.assertGreaterEqual(closes_at, before + timedelta(days=1))
        self.assertLess(closes_at, timezone.now() + timedelta(days=1, minutes=1))

    def test_unknown_duration_is_rejected(self):
        response = self.create(duration="forever")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Poll.objects.count(), 0)

    def test_form_shows_the_duration_select_and_detail_shows_closing_time(self):
        self.assertContains(self.client.get(reverse("polls:create")), 'name="duration"')
        self.create(duration="3d")
        response = self.client.get(Poll.objects.get().get_absolute_url())
        self.assertContains(response, "tarihinde kapanır")


class LazyCloseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_expired_poll_is_marked_closed_when_read(self):
        poll = make_poll(self.author, closes_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(poll.status, Poll.Status.ACTIVE)
        response = self.client.get(poll.get_absolute_url())
        self.assertContains(response, "Bu anket kapandı.")
        self.assertEqual(Poll.objects.get(pk=poll.pk).status, Poll.Status.CLOSED)

    def test_future_poll_stays_open(self):
        poll = make_poll(self.author, closes_at=timezone.now() + timedelta(hours=1))
        services.close_if_expired(poll)
        self.assertEqual(Poll.objects.get(pk=poll.pk).status, Poll.Status.ACTIVE)

    def test_votes_on_an_expired_poll_are_refused(self):
        poll = make_poll(self.author, closes_at=timezone.now() - timedelta(minutes=1))
        response = self.client.post(
            reverse("polls:vote", args=[poll.public_id]),
            {"option_id": poll.options.first().pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Poll.objects.get(pk=poll.pk).total_votes, 0)

    def test_expired_poll_moves_to_the_closed_tab(self):
        poll = make_poll(self.author, closes_at=timezone.now() - timedelta(minutes=1))
        closed = self.client.get(reverse("polls:index"), {"tab": "kapananlar"})
        self.assertIn(poll, closed.context["polls"])


class ShareAndCardMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        cls.poll = make_poll(cls.author, counts=(3, 7))

    def test_detail_has_hidden_share_and_card_buttons_and_scripts(self):
        response = self.client.get(self.poll.get_absolute_url())
        self.assertContains(response, "data-share")
        self.assertContains(response, f'data-url="http://testserver{self.poll.get_absolute_url()}"')
        self.assertContains(response, "data-card")
        self.assertContains(response, "js/share.js")
        self.assertContains(response, "js/card.js")
        # JS kapalıyken butonlar görünmez.
        html = response.content.decode()
        self.assertRegex(html, r"data-share[^>]*hidden>")
        self.assertRegex(html, r"data-card[^>]*hidden>")

    def test_question_with_quotes_does_not_break_the_attribute(self):
        poll = make_poll(self.author, question='Hangisi "daha" iyi olur acaba?')
        self.assertContains(self.client.get(poll.get_absolute_url()), "&quot;daha&quot;")


class HoneypotTests(TestCase):
    def register(self, **extra):
        return Client().post(reverse("accounts:register"), {
            "username": "ayse",
            "email": "ayse@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
            **extra,
        })

    def test_register_page_contains_the_hidden_trap_field(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertContains(response, 'name="website"')
        self.assertContains(response, 'aria-hidden="true"')
        self.assertContains(response, 'tabindex="-1"')

    def test_filled_trap_creates_no_account(self):
        response = self.register(website="http://spam.example")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kayıt tamamlanamadı.")
        self.assertEqual(User.objects.count(), 0)

    def test_empty_trap_registers_normally(self):
        self.assertEqual(self.register(website="").status_code, 302)
        self.assertEqual(User.objects.count(), 1)
