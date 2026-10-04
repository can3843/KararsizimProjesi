from django.shortcuts import render
from django.urls import reverse

from . import limits, services


class LoginRateLimitMiddleware:
    """Site ve admin giriş formlarına yapılan başarısız denemeleri IP ve kullanıcı adı başına sınırlar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _checks(self, request):
        """(sınır, tanımlayıcı) çiftleri; yalnızca giriş formu POST'larında dolu döner."""
        if request.method != "POST":
            return []
        ip = services.client_ip(request)
        username = request.POST.get("username", "").strip().lower()[:150]
        if request.path == reverse("admin:login"):
            checks = [(limits.ADMIN_LOGIN_IP, ip)]
        elif request.path == reverse("accounts:login"):
            checks = [(limits.LOGIN_IP, ip)]
        else:
            return []
        if username:
            checks.append((limits.LOGIN_USER, username))
        return checks

    def __call__(self, request):
        checks = self._checks(request)
        if any(services.is_limited(limit, identifier) for limit, identifier in checks):
            response = render(request, "429.html", status=429)
            response["Retry-After"] = str(int(max(limit.window for limit, _ in checks).total_seconds()))
            return response

        response = self.get_response(request)
        # Başarılı giriş yönlendirir (302); formun hata ile yeniden gösterilmesi başarısızlıktır.
        if checks and response.status_code == 200:
            for limit, identifier in checks:
                services.record(limit, identifier)
        return response
