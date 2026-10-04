from django.db import models
from django.utils import timezone


class RateLimitHit(models.Model):
    """Hız sınırı için tek bir olay. `scope`, ham IP/kullanıcı adı yerine tuzlu özet içerir."""

    scope = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["scope", "created_at"], name="ratelimit_scope_time_idx")]

    def __str__(self):
        return self.scope
