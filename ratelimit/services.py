import hashlib
import ipaddress
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import RateLimitHit

CLEANUP_PROBABILITY = 0.02
RETENTION = 2  # gün; en uzun pencere 24 saattir


def client_ip(request):
    """Vercel gerçek istemci adresini X-Vercel-Forwarded-For ile verir; yerelde REMOTE_ADDR."""
    meta = request.META
    raw = ""
    if settings.SECURE_DEPLOYMENT:
        raw = (meta.get("HTTP_X_VERCEL_FORWARDED_FOR") or meta.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    raw = raw or meta.get("REMOTE_ADDR", "")
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return raw
    if address.version == 6:
        # IPv6 kullanıcıları /64 bloğu içinde adres değiştirebildiğinden blok tek sayılır.
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
    return str(address)


def make_scope(limit, identifier):
    digest = hashlib.sha256(f"{identifier}|{settings.VOTER_KEY_SALT}".encode()).hexdigest()[:32]
    return f"{limit.name}:{digest}"


def is_limited(limit, identifier):
    since = timezone.now() - limit.window
    hits = RateLimitHit.objects.filter(scope=make_scope(limit, identifier), created_at__gte=since).count()
    return hits >= limit.count


def record(limit, identifier):
    RateLimitHit.objects.create(scope=make_scope(limit, identifier))
    if random.random() < CLEANUP_PROBABILITY:
        cleanup()


def cleanup():
    """Eski olayları ve süresi dolmuş oturumları siler (Vercel'de zamanlanmış iş olmadığından fırsat buldukça)."""
    now = timezone.now()
    RateLimitHit.objects.filter(created_at__lt=now - timedelta(days=RETENTION)).delete()
    Session.objects.filter(expire_date__lt=now).delete()
