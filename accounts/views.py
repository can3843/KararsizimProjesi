from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from ratelimit import limits
from ratelimit import services as ratelimit

from .forms import LoginForm, RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect("polls:index")

    form = RegisterForm(request.POST or None)
    ip = ratelimit.client_ip(request)
    if request.method == "POST" and form.is_valid():
        if ratelimit.is_limited(limits.REGISTER_IP, ip):
            form.add_error(None, "Bu bağlantıdan çok fazla hesap açıldı. Daha sonra tekrar dene.")
            return render(request, "accounts/register.html", {"form": form}, status=429)
        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            form.add_error(None, "Bu kullanıcı adı veya e-posta az önce alındı. Başka bir tane dene.")
        else:
            ratelimit.record(limits.REGISTER_IP, ip)
            login(request, user)
            messages.success(request, f"Hoş geldin, @{user.username}")
            return redirect("polls:index")
    return render(request, "accounts/register.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["login_required_notice"] = self.get_redirect_url().startswith("/anket/olustur/")
        return context
