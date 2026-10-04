from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from . import selectors, services
from .forms import PollForm


def _page_number(request):
    try:
        page = int(request.GET.get("page", 1))
    except ValueError:
        return 1
    return min(max(page, 1), selectors.MAX_PAGES)


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
    poll = selectors.get_poll(public_id)
    if poll is None:
        raise Http404
    selectors.decorate([poll], request.user)
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
