from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import selectors, services
from .forms import PollForm
from .utils import get_voter_key


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
    return poll


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
    page = _page_number(request)
    polls, has_more = selectors.feed(tab, page)
    selectors.decorate(polls, request.user)
    next_page = page + 1 if has_more and page < selectors.MAX_PAGES else None
    return render(request, "polls/index.html", {
        "polls": polls,
        "tab": tab,
        "tabs": selectors.TABS,
        "next_page": next_page,
        "load_more_url": f"?tab={tab}&page={next_page}",
    })


def detail(request, public_id):
    poll = _decorate_detail(request, _get_poll_or_404(public_id))
    return render(request, "polls/detail.html", {"poll": poll})


@login_required
def create(request):
    form = PollForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            poll = services.create_poll(
                request.user,
                form.cleaned_data["question"],
                form.cleaned_data["description"],
                form.cleaned_data["option_texts"],
            )
        except services.DailyLimitReached:
            form.add_error(
                None, f"Bugün en fazla {services.DAILY_POLL_LIMIT} anket açabilirsin. Yarın tekrar dene.",
            )
        else:
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
    voter_key = get_voter_key(request, create=True)
    user = request.user if request.user.is_authenticated else None
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
