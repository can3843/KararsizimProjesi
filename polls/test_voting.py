import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Option, Poll, Vote
from .tests import PASSWORD, make_poll

User = get_user_model()

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class VotingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "gizli.yazar@example.com", PASSWORD)
        cls.voter = User.objects.create_user("mehmet", "gizli.oyuncu@example.com", PASSWORD)
        cls.poll = make_poll(cls.author, counts=(0, 0, 0))
        cls.options = list(cls.poll.options.all())

    def vote_url(self, poll=None):
        return reverse("polls:vote", args=[(poll or self.poll).public_id])

    def cast(self, option, client=None, poll=None, ajax=True, **data):
        payload = {"option_id": option.pk if option is not None else "", **data}
        return (client or self.client).post(self.vote_url(poll), payload, **(AJAX if ajax else {}))

    def counters(self, poll=None):
        poll = Poll.objects.get(pk=(poll or self.poll).pk)
        return poll.total_votes, [option.vote_count for option in poll.options.all()]


class AnonymousVoteTests(VotingTestCase):
    def test_anonymous_vote_succeeds_and_increments_counters(self):
        response = self.cast(self.options[1])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.counters(), (1, [0, 1, 0]))
        vote = Vote.objects.get()
        self.assertIsNone(vote.user)
        self.assertEqual(vote.option, self.options[1])

    def test_success_payload_has_results_and_the_viewers_vote(self):
        data = self.cast(self.options[1]).json()
        self.assertEqual(data["message"], "Oyun kaydedildi.")
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["voted_option_id"], self.options[1].pk)
        self.assertTrue(data["is_open"])
        self.assertEqual([option["percent"] for option in data["options"]], [0, 100, 0])
        self.assertEqual([option["count"] for option in data["options"]], [0, 1, 0])

    def test_voter_key_is_a_salted_hash_of_the_session_key(self):
        self.cast(self.options[0])
        session_key = self.client.session.session_key
        expected = hashlib.sha256(f"{session_key}{settings.VOTER_KEY_SALT}".encode()).hexdigest()
        voter_key = Vote.objects.get().voter_key
        self.assertEqual(voter_key, expected)
        self.assertNotEqual(voter_key, session_key)
        self.assertEqual(len(voter_key), 64)

    def test_voted_poll_is_remembered_in_the_session(self):
        self.cast(self.options[0])
        self.assertEqual(self.client.session["voted_polls"], [self.poll.pk])

    def test_second_vote_from_same_session_is_409_and_changes_nothing(self):
        self.cast(self.options[0])
        response = self.cast(self.options[1])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "Bu ankete zaten oy verdin.")
        self.assertEqual(self.counters(), (1, [1, 0, 0]))
        self.assertEqual(Vote.objects.count(), 1)

    def test_conflict_response_contains_the_results(self):
        self.cast(self.options[0])
        data = self.cast(self.options[1]).json()
        self.assertEqual(data["voted_option_id"], self.options[0].pk)
        self.assertEqual([option["percent"] for option in data["options"]], [100, 0, 0])

    def test_different_sessions_can_each_vote_once(self):
        for option in (self.options[0], self.options[0], self.options[2]):
            self.assertEqual(self.cast(option, client=Client()).status_code, 200)
        self.assertEqual(self.counters(), (3, [2, 0, 1]))

    def test_concurrent_duplicate_is_caught_by_the_database_constraint(self):
        self.cast(self.options[0])
        # Uygulama kontrolü atlatılırsa (iki sekme aynı anda gönderirse) IntegrityError yakalanır.
        with patch("polls.services._has_voted", return_value=False):
            response = self.cast(self.options[1])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.counters(), (1, [1, 0, 0]))

    def test_counters_stay_consistent_with_votes(self):
        for option in (self.options[0], self.options[1], self.options[1]):
            self.cast(option, client=Client())
        for username in ("ayse", "mehmet"):
            client = Client()
            client.force_login(User.objects.get(username=username))
            self.cast(self.options[2], client=client)
        total, per_option = self.counters()
        self.assertEqual(total, 5)
        self.assertEqual(sum(per_option), 5)
        self.assertEqual(Vote.objects.filter(poll=self.poll).count(), 5)

    def test_cookie_clearing_visitor_can_vote_again(self):
        # Bilinen, kabul edilmiş sınır (şartname Bölüm 4.4).
        self.cast(self.options[0])
        self.assertEqual(self.cast(self.options[0], client=Client()).status_code, 200)


class AuthenticatedVoteTests(VotingTestCase):
    def test_vote_is_stored_with_user_and_voter_key(self):
        self.client.force_login(self.voter)
        self.assertEqual(self.cast(self.options[0]).status_code, 200)
        vote = Vote.objects.get()
        self.assertEqual(vote.user, self.voter)
        self.assertEqual(len(vote.voter_key), 64)

    def test_same_user_cannot_vote_twice_from_different_sessions(self):
        first, second = Client(), Client()
        first.force_login(self.voter)
        second.force_login(self.voter)
        self.assertEqual(self.cast(self.options[0], client=first).status_code, 200)
        response = self.cast(self.options[1], client=second)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.counters(), (1, [1, 0, 0]))

    def test_author_can_vote_on_own_poll(self):
        self.client.force_login(self.author)
        self.assertEqual(self.cast(self.options[0]).status_code, 200)
        self.assertEqual(self.counters(), (1, [1, 0, 0]))


class InvalidVoteTests(VotingTestCase):
    def test_option_of_another_poll_is_400(self):
        other_poll = make_poll(self.author, "Başka bir anketin sorusu burada", counts=(0, 0))
        response = self.cast(other_poll.options.first())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.counters(), (0, [0, 0, 0]))
        self.assertEqual(self.counters(other_poll), (0, [0, 0]))
        self.assertFalse(Vote.objects.exists())

    def test_missing_or_malformed_option_is_400(self):
        for value in ["", "abc", "-1", "0", "9" * 40]:
            with self.subTest(value=value):
                response = self.client.post(self.vote_url(), {"option_id": value}, **AJAX)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(self.vote_url(), {}, **AJAX).status_code, 400)
        self.assertFalse(Vote.objects.exists())

    def test_closed_poll_is_403_and_returns_results(self):
        closed = make_poll(self.author, "Kapalı anketin sorusu burada", counts=(2, 1), status=Poll.Status.CLOSED)
        response = self.cast(closed.options.first(), poll=closed)
        self.assertEqual(response.status_code, 403)
        self.assertEqual([option["percent"] for option in response.json()["options"]], [67, 33])
        self.assertEqual(self.counters(closed), (3, [2, 1]))

    def test_expired_poll_is_403(self):
        expired = make_poll(
            self.author, "Süresi dolmuş anketin sorusu", counts=(0, 0),
            closes_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertEqual(self.cast(expired.options.first(), poll=expired).status_code, 403)
        self.assertEqual(self.counters(expired), (0, [0, 0]))

    def test_unknown_poll_is_404(self):
        response = self.client.post(reverse("polls:vote", args=["yokböyleid"]), {"option_id": 1}, **AJAX)
        self.assertEqual(response.status_code, 404)

    def test_vote_url_only_accepts_post(self):
        self.assertEqual(self.client.get(self.vote_url()).status_code, 405)

    def test_csrf_token_is_required(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.vote_url(), {"option_id": self.options[0].pk}, **AJAX)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Vote.objects.exists())


class NoJavascriptVoteTests(VotingTestCase):
    def test_success_redirects_to_detail_with_results_and_toast(self):
        response = self.cast(self.options[0], ajax=False)
        self.assertRedirects(response, self.poll.get_absolute_url(), fetch_redirect_response=False)
        page = self.client.get(self.poll.get_absolute_url())
        self.assertContains(page, "Oyun kaydedildi.")
        self.assertContains(page, "%100")
        self.assertEqual(page.context["poll"].voted_option_id, self.options[0].pk)
        self.assertNotContains(page, 'name="option_id"')

    def test_duplicate_vote_renders_the_page_with_409(self):
        self.cast(self.options[0], ajax=False)
        response = self.cast(self.options[1], ajax=False)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Bu ankete zaten oy verdin.", status_code=409)

    def test_invalid_option_renders_the_page_with_400(self):
        response = self.cast(None, ajax=False)
        self.assertContains(response, "Geçerli bir seçenek seç.", status_code=400)

    def test_closed_poll_renders_the_page_with_403(self):
        closed = make_poll(self.author, "Kapalı anketin sorusu burada", counts=(1, 1), status=Poll.Status.CLOSED)
        response = self.cast(closed.options.first(), poll=closed, ajax=False)
        self.assertContains(response, "Bu anket kapandı", status_code=403)

    def test_json_is_chosen_by_the_accept_header_too(self):
        response = self.client.post(
            self.vote_url(), {"option_id": self.options[0].pk}, HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")


class DetailPageVotingStateTests(VotingTestCase):
    def test_open_poll_offers_radio_options_and_a_vote_button(self):
        page = self.client.get(self.poll.get_absolute_url())
        content = page.content.decode()
        self.assertEqual(content.count('type="radio" name="option_id"'), 3)
        self.assertContains(page, ">Oy ver</button>")
        self.assertContains(page, "csrfmiddlewaretoken")

    def test_closed_poll_has_no_vote_controls(self):
        closed = make_poll(self.author, "Kapalı anketin sorusu burada", counts=(1, 1), status=Poll.Status.CLOSED)
        page = self.client.get(closed.get_absolute_url())
        self.assertNotContains(page, 'name="option_id"')
        self.assertNotContains(page, ">Oy ver</button>")
        self.assertContains(page, "Bu anket kapandı.")

    def test_voter_sees_percentages_and_own_choice_after_voting(self):
        other = make_poll(self.author, "Oy verilen anketin sorusu", counts=(1, 1))
        self.cast(other.options.first(), poll=other)
        page = self.client.get(other.get_absolute_url())
        self.assertContains(page, "%67")
        self.assertContains(page, "%33")
        self.assertContains(page, "Oyunu verdin.")
        self.assertEqual(page.context["poll"].voted_option_id, other.options.first().pk)

    def test_other_visitors_still_do_not_see_percentages(self):
        other = make_poll(self.author, "Oy verilen anketin sorusu", counts=(1, 1))
        self.cast(other.options.first(), poll=other)
        page = self.client_class().get(other.get_absolute_url())
        self.assertNotContains(page, "%67")
        self.assertNotContains(page, "%33")

    def test_author_sees_percentages_and_can_still_vote(self):
        poll = make_poll(self.author, "Sahibinin anketinin sorusu", counts=(3, 1))
        self.client.force_login(self.author)
        page = self.client.get(poll.get_absolute_url())
        self.assertContains(page, "%75")
        self.assertContains(page, 'name="option_id"')

    def test_logged_in_voter_sees_results_on_other_devices(self):
        first, second = Client(), Client()
        first.force_login(self.voter)
        second.force_login(self.voter)
        self.cast(self.options[0], client=first)
        page = second.get(self.poll.get_absolute_url())
        self.assertContains(page, "%100")
        self.assertNotContains(page, 'name="option_id"')


class ResultsEndpointTests(VotingTestCase):
    def url(self, poll=None):
        return reverse("polls:results", args=[(poll or self.poll).public_id])

    def test_shape(self):
        data = self.client.get(self.url()).json()
        self.assertEqual(set(data), {"total", "options", "voted_option_id", "is_open", "badge"})
        self.assertEqual(set(data["options"][0]), {"id", "text", "count", "percent"})
        self.assertEqual(data["badge"], {"level": "empty", "text": "İlk oyu sen ver"})

    def test_numbers_are_hidden_before_voting(self):
        poll = make_poll(self.author, "Gizli sonuçlu anketin sorusu", counts=(6, 4))
        data = self.client.get(self.url(poll)).json()
        self.assertEqual(data["total"], 10)
        self.assertIsNone(data["voted_option_id"])
        self.assertTrue(all(option["percent"] is None and option["count"] is None for option in data["options"]))

    def test_numbers_are_visible_after_voting(self):
        poll = make_poll(self.author, "Oy verince açılan anketin sorusu", counts=(6, 4))
        self.cast(poll.options.last(), poll=poll)
        data = self.client.get(self.url(poll)).json()
        self.assertEqual(data["voted_option_id"], poll.options.last().pk)
        self.assertEqual([option["percent"] for option in data["options"]], [55, 45])

    def test_numbers_are_visible_for_closed_polls_and_the_author(self):
        closed = make_poll(self.author, "Kapalı sonuçlu anketin sorusu", counts=(3, 7), status=Poll.Status.CLOSED)
        self.assertEqual(
            [option["percent"] for option in self.client.get(self.url(closed)).json()["options"]], [30, 70]
        )
        open_poll = make_poll(self.author, "Sahibine açık anketin sorusu", counts=(3, 7))
        self.client.force_login(self.author)
        self.assertEqual(
            [option["percent"] for option in self.client.get(self.url(open_poll)).json()["options"]], [30, 70]
        )

    def test_percentages_always_sum_to_100(self):
        poll = make_poll(self.author, "Bölünmeyen sayılı anketin sorusu", counts=(1, 1, 1), status=Poll.Status.CLOSED)
        data = self.client.get(self.url(poll)).json()
        self.assertEqual(sum(option["percent"] for option in data["options"]), 100)

    def test_payload_never_leaks_emails_or_user_ids(self):
        self.client.force_login(self.voter)
        self.cast(self.options[0])
        for client in (self.client, Client()):
            body = client.get(self.url()).content.decode()
            self.assertNotIn("example.com", body)
            self.assertNotIn("user", body)
            self.assertNotIn("author", body)
            self.assertNotIn("voter", body)
        vote_body = self.cast(self.options[0], client=Client()).content.decode()
        self.assertNotIn("example.com", vote_body)

    def test_only_get_is_allowed_and_unknown_poll_is_404(self):
        self.assertEqual(self.client.post(self.url()).status_code, 405)
        self.assertEqual(self.client.get(reverse("polls:results", args=["yokböyleid"])).status_code, 404)

    def test_response_is_not_cached(self):
        self.assertIn("no-cache", self.client.get(self.url())["Cache-Control"])


class CloseAndDeleteTests(VotingTestCase):
    def close_url(self, poll=None):
        return reverse("polls:close", args=[(poll or self.poll).public_id])

    def delete_url(self, poll=None):
        return reverse("polls:delete", args=[(poll or self.poll).public_id])

    def test_owner_can_close_the_poll(self):
        self.client.force_login(self.author)
        response = self.client.post(self.close_url())
        self.assertRedirects(response, self.poll.get_absolute_url(), fetch_redirect_response=False)
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.status, Poll.Status.CLOSED)
        self.assertEqual(self.cast(self.options[0], client=Client()).status_code, 403)
        self.assertContains(self.client.get(self.poll.get_absolute_url()), "Anket kapatıldı.")

    def test_non_owner_cannot_close(self):
        self.client.force_login(self.voter)
        self.assertEqual(self.client.post(self.close_url()).status_code, 403)
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.status, Poll.Status.ACTIVE)

    def test_anonymous_close_goes_to_login_and_changes_nothing(self):
        response = self.client.post(self.close_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn("/giris/", response["Location"])
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.status, Poll.Status.ACTIVE)

    def test_close_requires_post(self):
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(self.close_url()).status_code, 405)

    def test_owner_sees_owner_actions_and_others_do_not(self):
        self.client.force_login(self.author)
        page = self.client.get(self.poll.get_absolute_url())
        self.assertContains(page, "Anketi kapat")
        self.assertContains(page, "Anketi sil")
        other = Client()
        other.force_login(self.voter)
        page = other.get(self.poll.get_absolute_url())
        self.assertNotContains(page, "Anketi kapat")
        self.assertNotContains(page, "Anketi sil")
        self.assertNotContains(self.client_class().get(self.poll.get_absolute_url()), "Anketi sil")

    def test_delete_asks_for_confirmation_first(self):
        self.client.force_login(self.author)
        response = self.client.get(self.delete_url())
        self.assertContains(response, "Bu işlem geri alınamaz.")
        self.assertContains(response, "Evet, anketi sil")
        self.assertTrue(Poll.objects.filter(pk=self.poll.pk).exists())

    def test_owner_can_delete_and_everything_cascades(self):
        self.cast(self.options[0], client=Client())
        self.client.force_login(self.author)
        response = self.client.post(self.delete_url())
        self.assertRedirects(
            response, reverse("polls:profile", args=["ayse"]), fetch_redirect_response=False,
        )
        self.assertFalse(Poll.objects.filter(pk=self.poll.pk).exists())
        self.assertFalse(Option.objects.filter(poll_id=self.poll.pk).exists())
        self.assertFalse(Vote.objects.exists())

    def test_non_owner_cannot_delete_or_see_confirmation(self):
        self.client.force_login(self.voter)
        self.assertEqual(self.client.get(self.delete_url()).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url()).status_code, 403)
        self.assertTrue(Poll.objects.filter(pk=self.poll.pk).exists())

    def test_anonymous_delete_goes_to_login_and_changes_nothing(self):
        for method in (self.client.get, self.client.post):
            response = method(self.delete_url())
            self.assertEqual(response.status_code, 302)
            self.assertIn("/giris/", response["Location"])
        self.assertTrue(Poll.objects.filter(pk=self.poll.pk).exists())


class VotingPrivacyTests(VotingTestCase):
    def test_voter_emails_are_not_rendered(self):
        self.client.force_login(self.voter)
        self.cast(self.options[0])
        for url in (self.poll.get_absolute_url(), reverse("polls:index"), reverse("polls:profile", args=["mehmet"])):
            with self.subTest(url=url):
                body = self.client.get(url).content.decode()
                self.assertNotIn("gizli.oyuncu@example.com", body)
                self.assertNotIn("gizli.yazar@example.com", body)
