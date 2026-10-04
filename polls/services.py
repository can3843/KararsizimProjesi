from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import Option, Poll, Vote

DAILY_POLL_LIMIT = 10


class DailyLimitReached(Exception):
    pass


class VoteError(Exception):
    pass


class PollClosed(VoteError):
    pass


class InvalidOption(VoteError):
    pass


class AlreadyVoted(VoteError):
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


def _has_voted(poll, user, voter_key):
    votes = Vote.objects.filter(poll=poll)
    if user is not None:
        return votes.filter(user=user).exists()
    return votes.filter(user__isnull=True, voter_key=voter_key).exists()


def cast_vote(poll, option, user, voter_key):
    """Oyu kaydeder. `option` ankete ait değilse (ya da None ise) InvalidOption fırlatır."""
    if not poll.is_open:
        raise PollClosed
    if option is None or option.poll_id != poll.pk:
        raise InvalidOption
    if _has_voted(poll, user, voter_key):
        raise AlreadyVoted

    try:
        with transaction.atomic():
            Vote.objects.create(poll=poll, option=option, user=user, voter_key=voter_key)
            Option.objects.filter(pk=option.pk).update(vote_count=F("vote_count") + 1)
            Poll.objects.filter(pk=poll.pk).update(total_votes=F("total_votes") + 1)
    except IntegrityError:
        # Aynı anda gelen ikinci istek: kısıt devreye girer, sayaçlar artmaz.
        raise AlreadyVoted from None


def close_poll(poll):
    Poll.objects.filter(pk=poll.pk).update(status=Poll.Status.CLOSED)


def delete_poll(poll):
    poll.delete()
