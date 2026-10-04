from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Option, Poll

DAILY_POLL_LIMIT = 10


class DailyLimitReached(Exception):
    pass


@transaction.atomic
def create_poll(author, question, description, option_texts):
    # Yazar satırını kilitlemek, aynı anda gelen isteklerin günlük sınırı aşmasını önler.
    get_user_model().objects.select_for_update().get(pk=author.pk)

    day_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    if Poll.objects.filter(author=author, created_at__gte=day_start).count() >= DAILY_POLL_LIMIT:
        raise DailyLimitReached

    poll = Poll.objects.create(author=author, question=question, description=description)
    Option.objects.bulk_create(
        Option(poll=poll, text=text, position=position) for position, text in enumerate(option_texts)
    )
    return poll
