import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.template import Context, Template
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Option, Poll, Vote
from .utils import compute_percentages, decision_badge

User = get_user_model()

PASSWORD = "gizli-sifre-2026"
LONG_QUESTION = "Bugün sinemaya mı gitsem, restorana mı?"


def make_poll(author, question=LONG_QUESTION, counts=(0, 0), **fields):
    poll = Poll.objects.create(author=author, question=question, total_votes=sum(counts), **fields)
    for position, count in enumerate(counts):
        Option.objects.create(poll=poll, text=f"Seçenek {position + 1}", position=position, vote_count=count)
    return poll


def add_votes(poll, count, days_ago=0):
    option = poll.options.first()
    created = [
        Vote.objects.create(poll=poll, option=option, voter_key=f"{poll.pk}-{days_ago}-{i}-{random.random()}")
        for i in range(count)
    ]
    Vote.objects.filter(pk__in=[vote.pk for vote in created]).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )


class VoteConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        cls.poll = Poll.objects.create(question=LONG_QUESTION, author=cls.user)
        cls.option_a = Option.objects.create(poll=cls.poll, text="Sinema", position=0)
        cls.option_b = Option.objects.create(poll=cls.poll, text="Restoran", position=1)

    def test_same_user_cannot_vote_twice(self):
        Vote.objects.create(poll=self.poll, option=self.option_a, user=self.user, voter_key="k1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Vote.objects.create(poll=self.poll, option=self.option_b, user=self.user, voter_key="k2")

    def test_same_anonymous_key_cannot_vote_twice(self):
        Vote.objects.create(poll=self.poll, option=self.option_a, voter_key="anon")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Vote.objects.create(poll=self.poll, option=self.option_b, voter_key="anon")

    def test_different_anonymous_keys_can_vote(self):
        Vote.objects.create(poll=self.poll, option=self.option_a, voter_key="anon-1")
        Vote.objects.create(poll=self.poll, option=self.option_a, voter_key="anon-2")
        self.assertEqual(Vote.objects.count(), 2)

    def test_option_position_is_unique_per_poll(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Option.objects.create(poll=self.poll, text="Başka", position=0)


class PercentageTests(TestCase):
    def test_indivisible_counts_sum_to_100(self):
        self.assertEqual(compute_percentages([3, 7]), [30, 70])
        self.assertEqual(sum(compute_percentages([1, 1, 1])), 100)
        self.assertEqual(compute_percentages([1, 1, 1]), [34, 33, 33])

    def test_zero_votes(self):
        self.assertEqual(compute_percentages([0, 0, 0]), [0, 0, 0])

    def test_percentages_always_sum_to_100(self):
        rng = random.Random(7)
        for _ in range(500):
            counts = [rng.randint(0, 50) for _ in range(rng.randint(2, 5))]
            if sum(counts):
                self.assertEqual(sum(compute_percentages(counts)), 100, counts)


class DecisionBadgeTests(TestCase):
    def test_thresholds(self):
        # Sınırlar: fark ≤5 → split, 6–20 → close, >20 → clear.
        cases = [
            ([50, 50], "split"), ([52, 47, 1], "split"),
            ([53, 47], "close"), ([60, 40], "close"),
            ([61, 39], "clear"), ([60, 20, 20], "clear"), ([90, 10], "clear"),
        ]
        for percents, level in cases:
            with self.subTest(percents=percents):
                self.assertEqual(decision_badge(percents, total=10)[0], level)

    def test_gap_is_between_the_two_leading_options(self):
        self.assertEqual(decision_badge([10, 45, 45], total=10)[0], "split")

    def test_texts(self):
        self.assertEqual(decision_badge([50, 50], 10), ("split", "Kalabalık da kararsız"))
        self.assertEqual(decision_badge([60, 40], 10), ("close", "Az farkla önde"))
        self.assertEqual(decision_badge([90, 10], 10), ("clear", "Karar net"))

    def test_empty_poll(self):
        self.assertEqual(decision_badge([0, 0], 0), ("empty", "İlk oyu sen ver"))
        self.assertEqual(decision_badge([0, 0], 0, is_open=False)[1], "Kimse oy vermedi")


class RelativeTimeTests(TestCase):
    def render(self, delta):
        template = Template("{% load polls_extras %}{{ value|relative_time }}")
        return template.render(Context({"value": timezone.now() - delta}))

    def test_units(self):
        self.assertEqual(self.render(timedelta(seconds=10)), "az önce")
        self.assertEqual(self.render(timedelta(minutes=5, seconds=3)), "5 dakika önce")
        self.assertEqual(self.render(timedelta(hours=3, minutes=20)), "3 saat önce")
        self.assertEqual(self.render(timedelta(days=2, hours=1)), "2 gün önce")

    def test_old_dates_are_absolute(self):
        self.assertRegex(self.render(timedelta(days=40)), r"^\d{1,2} \w+ \d{4}$")


class CreatePollTests(TestCase):
    url = reverse("polls:create")

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def post(self, options=("Sinema", "Restoran"), question=LONG_QUESTION, **extra):
        return self.client.post(self.url, {"question": question, "option": list(options), **extra})

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, "/giris/?next=/anket/olustur/", fetch_redirect_response=False)

    def test_anonymous_post_is_redirected_and_creates_nothing(self):
        response = self.post()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Poll.objects.count(), 0)

    def test_form_renders_five_option_inputs_without_javascript(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.content.decode().count('name="option"'), 5)

    def test_creates_poll_with_ordered_options(self):
        self.client.force_login(self.user)
        response = self.post(options=["Sinema", "Restoran", "Evde kal"], description="Hafta sonu planı")
        poll = Poll.objects.get()
        self.assertRedirects(response, poll.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(poll.author, self.user)
        self.assertEqual(poll.description, "Hafta sonu planı")
        self.assertEqual(poll.status, Poll.Status.ACTIVE)
        self.assertEqual(
            list(poll.options.values_list("text", "position")),
            [("Sinema", 0), ("Restoran", 1), ("Evde kal", 2)],
        )
        self.assertContains(self.client.get(poll.get_absolute_url()), "Anketin yayında.")

    def test_two_options_are_enough(self):
        self.client.force_login(self.user)
        self.post(options=["Sinema", "Restoran", "", "", ""])
        self.assertEqual(Poll.objects.get().options.count(), 2)

    def test_blank_rows_are_ignored_and_positions_are_compacted(self):
        self.client.force_login(self.user)
        self.post(options=["Sinema", "", "  ", "Restoran", ""])
        self.assertEqual(
            list(Poll.objects.get().options.values_list("text", "position")),
            [("Sinema", 0), ("Restoran", 1)],
        )

    def test_one_option_is_rejected(self):
        self.client.force_login(self.user)
        response = self.post(options=["Sinema", "", "", "", ""])
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "options", "En az 2 seçenek gerekli.")
        self.assertContains(response, "En az 2 seçenek gerekli.")
        self.assertEqual(Poll.objects.count(), 0)

    def test_no_options_is_rejected(self):
        self.client.force_login(self.user)
        response = self.post(options=["", "", "", "", ""])
        self.assertFormError(response.context["form"], "options", "En az 2 seçenek gerekli.")

    def test_six_options_are_rejected(self):
        self.client.force_login(self.user)
        response = self.post(options=["A", "B", "C", "D", "E", "F"])
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "options", "En fazla 5 seçenek olabilir.")
        self.assertEqual(Poll.objects.count(), 0)

    def test_duplicate_options_are_rejected_case_insensitively(self):
        self.client.force_login(self.user)
        response = self.post(options=["Sinema", "sinema"])
        self.assertFormError(response.context["form"], "options", "Aynı seçenek iki kez yazılamaz.")
        self.assertEqual(Poll.objects.count(), 0)

    def test_overlong_option_is_rejected(self):
        self.client.force_login(self.user)
        response = self.post(options=["A" * 81, "B"])
        self.assertIn("options", response.context["form"].errors)

    def test_question_length_is_validated(self):
        self.client.force_login(self.user)
        for question in ["Kısa?", "x" * 141, "   "]:
            with self.subTest(question=question):
                response = self.post(question=question)
                self.assertEqual(response.status_code, 200)
                self.assertIn("question", response.context["form"].errors)
        self.assertEqual(Poll.objects.count(), 0)

    def test_entered_values_survive_validation_errors(self):
        self.client.force_login(self.user)
        response = self.post(options=["Sinema", "", "", "Restoran", ""], question="Kısa?")
        self.assertContains(response, 'value="Restoran"')

    def test_daily_limit(self):
        self.client.force_login(self.user)
        for _ in range(services.DAILY_POLL_LIMIT):
            make_poll(self.user)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bugün en fazla 10 anket açabilirsin.")
        self.assertEqual(Poll.objects.count(), services.DAILY_POLL_LIMIT)

    def test_polls_from_earlier_days_do_not_count_towards_the_limit(self):
        self.client.force_login(self.user)
        for _ in range(services.DAILY_POLL_LIMIT):
            make_poll(self.user)
        Poll.objects.update(created_at=timezone.now() - timedelta(days=1, hours=1))
        self.post()
        self.assertEqual(Poll.objects.count(), services.DAILY_POLL_LIMIT + 1)

    def test_daily_limit_is_per_user(self):
        other = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        for _ in range(services.DAILY_POLL_LIMIT):
            make_poll(other)
        self.client.force_login(self.user)
        self.post()
        self.assertEqual(Poll.objects.filter(author=self.user).count(), 1)


class FeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_empty_state(self):
        response = self.client.get(reverse("polls:index"))
        self.assertContains(response, "Henüz anket yok. İlk kararsızlığını sen paylaş.")

    def test_lists_newest_first(self):
        first = make_poll(self.author, "Birinci anket sorusu burada")
        second = make_poll(self.author, "İkinci anket sorusu burada")
        polls = self.client.get(reverse("polls:index")).context["polls"]
        self.assertEqual([p.pk for p in polls], [second.pk, first.pk])

    def test_card_shows_author_votes_and_badge(self):
        make_poll(self.author, counts=(5, 5))
        response = self.client.get(reverse("polls:index"))
        self.assertContains(response, LONG_QUESTION)
        self.assertContains(response, "@ayse")
        self.assertContains(response, "10 oy")
        self.assertContains(response, "Kalabalık da kararsız")
        self.assertContains(response, "decision-bar")

    def test_pagination_shows_more_on_request(self):
        for number in range(25):
            make_poll(self.author, f"Sayfalama için {number:02d}. soru")
        first_page = self.client.get(reverse("polls:index"))
        self.assertEqual(len(first_page.context["polls"]), 20)
        self.assertContains(first_page, "Daha fazla göster")
        self.assertContains(first_page, "?tab=yeni&amp;page=2")

        second_page = self.client.get(reverse("polls:index"), {"page": 2})
        self.assertEqual(len(second_page.context["polls"]), 25)
        self.assertNotContains(second_page, "Daha fazla göster")

    def test_no_load_more_button_when_everything_fits(self):
        for number in range(20):
            make_poll(self.author, f"Tam sayfa için {number:02d}. soru")
        response = self.client.get(reverse("polls:index"))
        self.assertEqual(len(response.context["polls"]), 20)
        self.assertNotContains(response, "Daha fazla göster")

    def test_invalid_page_falls_back_to_first_page(self):
        make_poll(self.author)
        for page in ["abc", "-3", "0", ""]:
            with self.subTest(page=page):
                response = self.client.get(reverse("polls:index"), {"page": page})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context["polls"]), 1)

    def test_unknown_tab_falls_back_to_new(self):
        make_poll(self.author)
        response = self.client.get(reverse("polls:index"), {"tab": "yok"})
        self.assertEqual(response.context["tab"], "yeni")

    def test_closed_polls_only_appear_in_the_closed_tab(self):
        open_poll = make_poll(self.author, "Açık olan anket sorusu")
        closed = make_poll(self.author, "Kapalı olan anket sorusu", status=Poll.Status.CLOSED)
        expired = make_poll(
            self.author, "Süresi dolan anket sorusu", closes_at=timezone.now() - timedelta(hours=1)
        )
        new_tab = self.client.get(reverse("polls:index"), {"tab": "yeni"}).context["polls"]
        closed_tab = self.client.get(reverse("polls:index"), {"tab": "kapananlar"}).context["polls"]
        self.assertEqual([p.pk for p in new_tab], [open_poll.pk])
        self.assertEqual({p.pk for p in closed_tab}, {closed.pk, expired.pk})

    def test_popular_tab_orders_by_votes_in_the_last_seven_days(self):
        old_favourite = make_poll(self.author, "Eskiden popüler olan soru")
        recent_favourite = make_poll(self.author, "Şimdi popüler olan soru")
        quiet = make_poll(self.author, "Sessiz kalan anket sorusu")
        add_votes(old_favourite, 10, days_ago=8)
        add_votes(recent_favourite, 3, days_ago=1)
        add_votes(quiet, 1, days_ago=0)
        polls = self.client.get(reverse("polls:index"), {"tab": "populer"}).context["polls"]
        self.assertEqual([p.pk for p in polls], [recent_favourite.pk, quiet.pk, old_favourite.pk])

    def count_queries(self, url, **params):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        return len(queries)

    def test_query_count_does_not_grow_with_the_number_of_polls(self):
        for tab in ["yeni", "populer", "kapananlar"]:
            with self.subTest(tab=tab):
                status = Poll.Status.CLOSED if tab == "kapananlar" else Poll.Status.ACTIVE
                Poll.objects.all().delete()
                for number in range(2):
                    make_poll(self.author, f"Az sayıda anket {number}. soru", counts=(3, 4, 5), status=status)
                small = self.count_queries(reverse("polls:index"), tab=tab)
                for number in range(30):
                    make_poll(self.author, f"Çok sayıda anket {number}. soru", counts=(3, 4, 5), status=status)
                large = self.count_queries(reverse("polls:index"), tab=tab)
                self.assertEqual(small, large)
                self.assertLessEqual(large, 3)

    def test_profile_query_count_is_constant(self):
        url = reverse("polls:profile", args=["ayse"])
        make_poll(self.author)
        small = self.count_queries(url)
        for _ in range(15):
            make_poll(self.author, counts=(1, 2, 3))
        self.assertEqual(small, self.count_queries(url))


class ResultVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        cls.visitor = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)

    def test_bar_and_badge_are_public_but_percentages_are_hidden_before_voting(self):
        poll = make_poll(self.author, counts=(6, 4))
        for url in [reverse("polls:index"), poll.get_absolute_url()]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "decision-bar__segment")
                self.assertContains(response, "Az farkla önde")
                self.assertNotContains(response, "option-row__percent")
                self.assertNotContains(response, "%60")

    def test_detail_hides_percentages_from_other_logged_in_users(self):
        poll = make_poll(self.author, counts=(6, 4))
        self.client.force_login(self.visitor)
        self.assertNotContains(self.client.get(poll.get_absolute_url()), "option-row__percent")

    def test_author_sees_percentages_without_voting(self):
        poll = make_poll(self.author, counts=(6, 4))
        self.client.force_login(self.author)
        response = self.client.get(poll.get_absolute_url())
        self.assertContains(response, "%60")
        self.assertContains(response, "%40")

    def test_closed_poll_shows_percentages_to_everyone(self):
        poll = make_poll(self.author, counts=(6, 4), status=Poll.Status.CLOSED)
        response = self.client.get(poll.get_absolute_url())
        self.assertContains(response, "%60")
        self.assertContains(response, "Kapandı")

    def test_empty_poll_invites_the_first_vote(self):
        poll = make_poll(self.author, counts=(0, 0))
        self.assertContains(self.client.get(poll.get_absolute_url()), "İlk oyu sen ver")


class DetailAndProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("KullaniciAdi", "gizli.adres@example.com", PASSWORD)
        cls.poll = make_poll(cls.author, counts=(2, 1, 0), description="Kısa bir açıklama")

    def test_detail_shows_poll(self):
        response = self.client.get(self.poll.get_absolute_url())
        self.assertContains(response, LONG_QUESTION)
        self.assertContains(response, "Kısa bir açıklama")
        self.assertContains(response, "@KullaniciAdi")
        self.assertContains(response, "3 kişi oy verdi")
        for position in (1, 2, 3):
            self.assertContains(response, f"Seçenek {position}")

    def test_unknown_poll_is_404(self):
        self.assertEqual(self.client.get(reverse("polls:detail", args=["yokböyleid"])).status_code, 404)

    def test_poll_url_uses_public_id(self):
        self.assertEqual(self.poll.get_absolute_url(), f"/anket/{self.poll.public_id}/")

    def test_create_route_is_not_swallowed_by_detail_route(self):
        self.assertEqual(self.client.get("/anket/olustur/").status_code, 302)

    def test_profile_shows_polls_and_totals(self):
        make_poll(self.author, "İkinci anket için soru metni", counts=(4, 4), status=Poll.Status.CLOSED)
        response = self.client.get(reverse("polls:profile", args=["KullaniciAdi"]))
        self.assertContains(response, "@KullaniciAdi")
        self.assertContains(response, "2 anket · 11 oy aldı")
        self.assertContains(response, LONG_QUESTION)
        self.assertContains(response, "İkinci anket için soru metni")

    def test_profile_lookup_is_case_insensitive(self):
        self.assertEqual(self.client.get("/kullanici/kullaniciadi/").status_code, 200)

    def test_unknown_profile_is_404(self):
        self.assertEqual(self.client.get("/kullanici/yok_boyle/").status_code, 404)

    def test_profile_for_user_without_polls_shows_empty_state(self):
        User.objects.create_user("bos_kullanici", "bos@example.com", PASSWORD)
        response = self.client.get("/kullanici/bos_kullanici/")
        self.assertContains(response, "0 anket · 0 oy aldı")
        self.assertContains(response, "Henüz anket yok.")

    def test_author_email_is_never_rendered(self):
        urls = [
            reverse("polls:index"),
            reverse("polls:index") + "?tab=populer",
            reverse("polls:index") + "?tab=kapananlar",
            self.poll.get_absolute_url(),
            reverse("polls:profile", args=["KullaniciAdi"]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "gizli.adres@example.com")
