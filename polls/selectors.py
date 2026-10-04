from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import Poll, Vote
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


def find_option(poll, raw_id):
    """Yalnızca bu ankete ait seçeneği döndürür; geçersiz ya da yabancı id için None."""
    try:
        option_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    return next((option for option in poll.options.all() if option.pk == option_id), None)


def get_profile_user(username):
    return get_user_model().objects.filter(username__iexact=username).first()


def user_polls(user, page):
    limit = page * PAGE_SIZE
    queryset = _with_relations(Poll.objects.filter(author=user))
    return _split_page(list(queryset[: limit + 1]), limit)


def user_stats(user):
    totals = Poll.objects.filter(author=user).aggregate(polls=Count("id"), votes=Sum("total_votes"))
    return {"poll_count": totals["polls"], "votes_received": totals["votes"] or 0}


def viewer_vote_option_id(poll, user, voter_key):
    votes = Vote.objects.filter(poll=poll)
    if user.is_authenticated:
        votes = votes.filter(user=user)
    elif voter_key:
        votes = votes.filter(user__isnull=True, voter_key=voter_key)
    else:
        return None
    return votes.values_list("option_id", flat=True).first()


def decorate(polls, viewer, voted_poll_ids=frozenset()):
    """Şablonların ihtiyaç duyduğu sonuç alanlarını hesaplar. `options` önceden çekilmiş olmalı."""
    viewer_id = viewer.pk if viewer.is_authenticated else None
    for poll in polls:
        options = list(poll.options.all())
        counts = [option.vote_count for option in options]
        percents = compute_percentages(counts)
        poll.open = poll.is_open
        # Yüzde rakamları oy vermeden önce gizlidir; oy verince, kapanınca ve sahibi için açıktır.
        poll.results_visible = (
            not poll.open or poll.author_id == viewer_id or poll.pk in voted_poll_ids
        )
        poll.rows = [
            {"index": index, "option": option, "percent": percent, "voted": False}
            for index, (option, percent) in enumerate(zip(options, percents))
        ]
        poll.badge_level, poll.badge_text = decision_badge(percents, sum(counts), poll.open)
        if poll.results_visible:
            poll.bar_label = ", ".join(f"{row['option'].text} %{row['percent']}" for row in poll.rows)
        else:
            poll.bar_label = "Oyların dağılımı. Yüzdeler oy verince açılır."
    return polls


def decorate_detail(poll, viewer, voter_key, session_voted_ids):
    """Detay sayfası için: izleyicinin oyunu ve oy verebilme durumunu da ekler."""
    voted_option_id = viewer_vote_option_id(poll, viewer, voter_key)
    has_voted = voted_option_id is not None or poll.pk in session_voted_ids
    decorate([poll], viewer, {poll.pk} if has_voted else frozenset())
    poll.has_voted = has_voted
    poll.voted_option_id = voted_option_id
    poll.can_vote = poll.open and not has_voted
    poll.is_owner = viewer.is_authenticated and poll.author_id == viewer.pk
    for row in poll.rows:
        row["voted"] = row["option"].pk == voted_option_id
    return poll


def results_payload(poll):
    """`/sonuc/` ve oy cevaplarının JSON gövdesi. Gizli olan sayılar null döner; kullanıcı bilgisi içermez."""
    visible = poll.results_visible
    return {
        "total": poll.total_votes,
        "options": [
            {
                "id": row["option"].pk,
                "text": row["option"].text,
                "count": row["option"].vote_count if visible else None,
                "percent": row["percent"] if visible else None,
            }
            for row in poll.rows
        ],
        "voted_option_id": poll.voted_option_id,
        "is_open": poll.open,
        "badge": {"level": poll.badge_level, "text": poll.badge_text},
    }
