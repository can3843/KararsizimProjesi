from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Option, Poll, Vote

User = get_user_model()


class VoteConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ayse", "ayse@example.com", "parola-12345")
        cls.poll = Poll.objects.create(question="Sinemaya mı gitsem, restorana mı?", author=cls.user)
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
