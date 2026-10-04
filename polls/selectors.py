from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import Poll
from .utils import compute_percentages, decision_badge

PAGE_SIZE = 20
MAX_PAGES = 25
POPULAR_WINDOW = timedelta(days=7)

TABS = (("yeni", "Yeni"), ("populer", "Popüler"), ("kapananlar", "Kapananlar"))
DEFAULT_TAB = TABS[0][0]


def _with_relations(queryset):
    return queryset.select_related("author").prefetch_related("options")


def _open_filter(now):
    return Q(status=Poll.Status.ACTIVE) & (Q(closes_at__isnull=True) | Q(closes_at__gt=now))


def _split_page(rows, limit):
    return rows[:limit], len(rows) > limit


def feed(tab, page):
    """Akış: ilk `page * PAGE_SIZE` kayıt ve devamı olup olmadığı. Sorgu sayısı sabittir."""
    now = timezone.now()
    queryset = _with_relations(Poll.objects.all())
    if tab == "kapananlar":
        queryset = queryset.exclude(_open_filter(now))
    else:
        queryset = queryset.filter(_open_filter(now))
        if tab == "populer":
            recent = Count("votes", filter=Q(votes__created_at__gte=now - POPULAR_WINDOW))
            queryset = queryset.annotate(recent_votes=recent).order_by("-recent_votes", "-created_at")
    limit = page * PAGE_SIZE
    return _split_page(list(queryset[: limit + 1]), limit)


def get_poll(public_id):
    return _with_relations(Poll.objects.filter(public_id=public_id)).first()


def get_profile_user(username):
    return get_user_model().objects.filter(username__iexact=username).first()


def user_polls(user, page):
    limit = page * PAGE_SIZE
    queryset = _with_relations(Poll.objects.filter(author=user))
    return _split_page(list(queryset[: limit + 1]), limit)


def user_stats(user):
    totals = Poll.objects.filter(author=user).aggregate(polls=Count("id"), votes=Sum("total_votes"))
    return {"poll_count": totals["polls"], "votes_received": totals["votes"] or 0}


def decorate(polls, viewer):
    """Şablonların ihtiyaç duyduğu sonuç alanlarını hesaplar. `options` önceden çekilmiş olmalı."""
    viewer_id = viewer.pk if viewer.is_authenticated else None
    for poll in polls:
        options = list(poll.options.all())
        counts = [option.vote_count for option in options]
        percents = compute_percentages(counts)
        poll.open = poll.is_open
        # Yüzde rakamları oy vermeden önce gizlidir; kapanınca ve sahibi için açıktır.
        poll.results_visible = not poll.open or poll.author_id == viewer_id
        poll.rows = [
            {"index": index, "option": option, "percent": percent}
            for index, (option, percent) in enumerate(zip(options, percents))
        ]
        poll.badge_level, poll.badge_text = decision_badge(percents, sum(counts), poll.open)
        if poll.results_visible:
            poll.bar_label = ", ".join(f"{row['option'].text} %{row['percent']}" for row in poll.rows)
        else:
            poll.bar_label = "Oyların dağılımı. Yüzdeler oy verince açılır."
    return polls
