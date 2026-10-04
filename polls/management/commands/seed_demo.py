import hashlib
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from polls.models import Option, Poll, Vote

DEMO_USERNAMES = ["demo_ayse", "demo_mehmet", "demo_zeynep"]

DEMO_POLLS = [
    ("Bugün sinemaya mı gitsem, restorana mı?", ["Sinema", "Restoran"]),
    ("Hafta sonu tatili için hangisi daha iyi?", ["Deniz kenarı", "Dağ evi", "Şehir turu"]),
    ("Yeni telefon alırken en çok neye bakmalıyım?", ["Kamera", "Pil ömrü", "Fiyat", "Ekran", "Marka"]),
    ("Sabah kahvesi mi, çay mı?", ["Kahve", "Çay"]),
    ("Akşam yemeği için ne sipariş edelim?", ["Pizza", "Hamburger", "Lahmacun", "Sushi"]),
    ("Yeni bir dil öğrenecek olsam hangisi olmalı?", ["İspanyolca", "Almanca", "Japonca", "Korece"]),
    ("Ev arkadaşımla film gecesi için hangi tür?", ["Komedi", "Korku", "Bilim kurgu"]),
    ("Sınav haftası çalışmak için en iyi yer neresi?", ["Kütüphane", "Kafe", "Evim"]),
    ("Doğum günü hediyesi olarak ne almalıyım?", ["Kitap", "Kulaklık", "Deneyim bileti", "Bitki", "Parfüm"]),
    ("Sabah sporu mu, akşam sporu mu?", ["Sabah", "Akşam"]),
    ("Tatilde araba kiralayalım mı yoksa toplu taşıma mı?", ["Araba kiralayalım", "Toplu taşıma"]),
    ("Kış için hangi şehre gitmeliyim?", ["Kapadokya", "Uludağ", "Erzurum", "Safranbolu"]),
]

CLOSED_POLL_INDEXES = {3, 7}
EMPTY_POLL_INDEXES = {11}


def _anon_key():
    return hashlib.sha256(random.randbytes(16)).hexdigest()


class Command(BaseCommand):
    help = "Demo kullanıcıları, anketleri ve rastgele oyları oluşturur."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Önce mevcut demo verisini sil.")
        parser.add_argument(
            "--password",
            help="Demo kullanıcılara bu parola verilir. Verilmezse giriş yapılamaz.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        existing = User.objects.filter(username__in=DEMO_USERNAMES)
        if existing.exists():
            if not options["reset"]:
                raise CommandError("Demo verisi zaten var. Yeniden oluşturmak için --reset kullan.")
            existing.delete()

        users = []
        for username in DEMO_USERNAMES:
            user = User(username=username, email=f"{username}@example.com")
            if options["password"]:
                user.set_password(options["password"])
            else:
                user.set_unusable_password()
            user.save()
            users.append(user)

        now = timezone.now()
        for index, (question, option_texts) in enumerate(DEMO_POLLS):
            poll = Poll.objects.create(
                question=question,
                author=users[index % len(users)],
                status=Poll.Status.CLOSED if index in CLOSED_POLL_INDEXES else Poll.Status.ACTIVE,
            )
            options = [
                Option.objects.create(poll=poll, text=text, position=position)
                for position, text in enumerate(option_texts)
            ]
            created_at = now - timedelta(days=random.randint(0, 12), hours=random.randint(0, 23))
            Poll.objects.filter(pk=poll.pk).update(created_at=created_at)

            if index not in EMPTY_POLL_INDEXES:
                self._add_votes(poll, options, users, created_at, now)
            self._refresh_counters(poll)

        self.stdout.write(self.style.SUCCESS(
            f"{len(users)} kullanıcı, {len(DEMO_POLLS)} anket ve rastgele oylar oluşturuldu."
        ))

    def _add_votes(self, poll, options, users, created_at, now):
        weights = [random.randint(1, 10) for _ in options]
        for user in random.sample(users, k=random.randint(0, len(users))):
            Vote.objects.create(
                poll=poll,
                option=random.choices(options, weights)[0],
                user=user,
                voter_key=_anon_key(),
            )
        for _ in range(random.randint(5, 60)):
            Vote.objects.create(
                poll=poll,
                option=random.choices(options, weights)[0],
                voter_key=_anon_key(),
            )
        span = max((now - created_at).total_seconds(), 1)
        for vote in Vote.objects.filter(poll=poll):
            offset = timedelta(seconds=random.uniform(0, span))
            Vote.objects.filter(pk=vote.pk).update(created_at=created_at + offset)

    def _refresh_counters(self, poll):
        counts = dict(
            Vote.objects.filter(poll=poll).values_list("option").annotate(n=Count("id"))
        )
        for option in poll.options.all():
            Option.objects.filter(pk=option.pk).update(vote_count=counts.get(option.pk, 0))
        Poll.objects.filter(pk=poll.pk).update(total_votes=sum(counts.values()))
