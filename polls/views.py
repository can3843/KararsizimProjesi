from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ratelimit import limits
from ratelimit import services as ratelimit

from . import selectors, services
from .forms import PollForm
from .models import Report
from .utils import get_voter_key


SEARCH_MAX_LENGTH = 100


def _page_number(request):
    try:
        page = int(request.GET.get("page", 1))
    except ValueError:
        return 1
    return min(max(page, 1), selectors.MAX_PAGES)


def _wants_json(request):
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )


def _get_poll_or_404(public_id):
    poll = selectors.get_poll(public_id)
    if poll is None:
        raise Http404
    return services.close_if_expired(poll)


def _decorate_detail(request, poll):
    return selectors.decorate_detail(
        poll,
        request.user,
        get_voter_key(request),
        set(request.session.get("voted_polls", [])),
    )


def _remember_vote(request, poll):
    voted = request.session.get("voted_polls", [])
    if poll.pk not in voted:
        request.session["voted_polls"] = [*voted, poll.pk]


def index(request):
    tab = request.GET.get("tab")
    if tab not in dict(selectors.TABS):
        tab = selectors.DEFAULT_TAB
    query = request.GET.get("q", "").strip()[:SEARCH_MAX_LENGTH]
    page = _page_number(request)
    polls, has_more = selectors.feed(tab, page, query)
    selectors.decorate(polls, request.user)
    next_page = page + 1 if has_more and page < selectors.MAX_PAGES else None
    params = {"tab": tab, **({"q": query} if query else {})}
    return render(request, "polls/index.html", {
        "polls": polls,
        "tab": tab,
        "tabs": [(key, label, urlencode({**params, "tab": key})) for key, label in selectors.TABS],
        "query": query,
        "next_page": next_page,
        "load_more_url": "?" + urlencode({**params, "page": next_page}),
    })


def detail(request, public_id):
    poll = _decorate_detail(request, _get_poll_or_404(public_id))
    return render(request, "polls/detail.html", {"poll": poll})


@login_required
def create(request):
    form = PollForm(request.POST or None)
    ip = ratelimit.client_ip(request)
    if request.method == "POST" and form.is_valid():
        if ratelimit.is_limited(limits.POLL_CREATE_IP, ip):
            form.add_error(None, "Bu bağlantıdan bugün çok fazla anket açıldı. Yarın tekrar dene.")
            return render(request, "polls/create.html", {"form": form}, status=429)
        try:
            poll = services.create_poll(
                request.user,
                form.cleaned_data["question"],
                form.cleaned_data["description"],
                form.cleaned_data["option_texts"],
                form.cleaned_data["closes_at"],
            )
        except services.DailyLimitReached:
            form.add_error(
                None, f"Bugün en fazla {services.DAILY_POLL_LIMIT} anket açabilirsin. Yarın tekrar dene.",
            )
        else:
            ratelimit.record(limits.POLL_CREATE_IP, ip)
            messages.success(request, "Anketin yayında.")
            return redirect(poll)
    return render(request, "polls/create.html", {"form": form})


def _vote_response(request, public_id, status, message):
    # Sayaçlar F() ile güncellendiği için anket yeniden okunur.
    poll = _decorate_detail(request, _get_poll_or_404(public_id))
    ok = status == 200
    if _wants_json(request):
        payload = selectors.results_payload(poll)
        payload["message" if ok else "error"] = message
        return JsonResponse(payload, status=status)
    (messages.success if ok else messages.error)(request, message)
    if ok:
        return redirect(poll)
    return render(request, "polls/detail.html", {"poll": poll}, status=status)


@require_POST
def vote(request, public_id):
    poll = _get_poll_or_404(public_id)
    user = request.user if request.user.is_authenticated else None
    ip = ratelimit.client_ip(request)

    if user is None:
        # Sınır, oturum yaratılmadan önce denetlenir: her çerezsiz istek yeni bir oturum satırı demektir.
        if ratelimit.is_limited(limits.VOTE_ATTEMPT_IP, ip) or ratelimit.is_limited(
            limits.VOTE_POLL_IP, f"{ip}|{poll.pk}"
        ):
            return _vote_response(request, public_id, 429, "Çok fazla oy denemesi yaptın. Biraz sonra tekrar dene.")
        ratelimit.record(limits.VOTE_ATTEMPT_IP, ip)

    voter_key = get_voter_key(request, create=True)
    option = selectors.find_option(poll, request.POST.get("option_id"))

    try:
        services.cast_vote(poll, option, user, voter_key)
    except services.PollClosed:
        return _vote_response(request, public_id, 403, "Bu anket kapandı, artık oy verilemez.")
    except services.InvalidOption:
        return _vote_response(request, public_id, 400, "Geçerli bir seçenek seç.")
    except services.AlreadyVoted:
        _remember_vote(request, poll)
        return _vote_response(request, public_id, 409, "Bu ankete zaten oy verdin.")

    if user is None:
        ratelimit.record(limits.VOTE_POLL_IP, f"{ip}|{poll.pk}")
    _remember_vote(request, poll)
    return _vote_response(request, public_id, 200, "Oyun kaydedildi.")


@require_GET
@never_cache
def results(request, public_id):
    poll = _decorate_detail(request, _get_poll_or_404(public_id))
    return JsonResponse(selectors.results_payload(poll))


def _get_owned_poll(request, public_id):
    poll = _get_poll_or_404(public_id)
    if poll.author_id != request.user.pk:
        raise PermissionDenied
    return poll


@require_POST
@login_required
def report(request, public_id):
    poll = _get_poll_or_404(public_id)
    reason = request.POST.get("reason")
    if poll.author_id == request.user.pk:
        messages.error(request, "Kendi anketini bildiremezsin.")
    elif reason not in Report.Reason.values:
        messages.error(request, "Bildirim nedenini seç.")
    elif ratelimit.is_limited(limits.REPORT_USER, request.user.pk):
        messages.error(request, "Bugün çok fazla bildirim gönderdin. Yarın tekrar dene.")
    else:
        ratelimit.record(limits.REPORT_USER, request.user.pk)
        services.report_poll(poll, request.user, reason)
        messages.success(request, "Bildirimin alındı, teşekkürler.")
    return redirect(poll)


@require_POST
@login_required
def close(request, public_id):
    poll = _get_owned_poll(request, public_id)
    services.close_poll(poll)
    messages.success(request, "Anket kapatıldı.")
    return redirect(poll)


@require_http_methods(["GET", "POST"])
@login_required
def delete(request, public_id):
    poll = _get_owned_poll(request, public_id)
    if request.method == "POST":
        services.delete_poll(poll)
        messages.success(request, "Anket silindi.")
        return redirect("polls:profile", username=request.user.username)
    return render(request, "polls/confirm_delete.html", {"poll": poll})


def profile(request, username):
    profile_user = selectors.get_profile_user(username)
    if profile_user is None:
        raise Http404
    page = _page_number(request)
    polls, has_more = selectors.user_polls(profile_user, page)
    selectors.decorate(polls, request.user)
    next_page = page + 1 if has_more and page < selectors.MAX_PAGES else None
    return render(request, "polls/profile.html", {
        "profile_user": profile_user,
        "stats": selectors.user_stats(profile_user),
        "polls": polls,
        "next_page": next_page,
        "load_more_url": f"?page={next_page}",
    })
