from datetime import timedelta
from typing import NamedTuple


class Limit(NamedTuple):
    name: str
    count: int
    window: timedelta


# Başarısız giriş denemeleri (site ve admin ortak sayılır).
LOGIN_IP = Limit("login-ip", 20, timedelta(minutes=15))
LOGIN_USER = Limit("login-user", 8, timedelta(minutes=15))
ADMIN_LOGIN_IP = Limit("admin-ip", 10, timedelta(minutes=15))

REGISTER_IP = Limit("register-ip", 5, timedelta(hours=24))
POLL_CREATE_IP = Limit("poll-ip", 20, timedelta(hours=24))
REPORT_USER = Limit("report-user", 10, timedelta(hours=24))

# Anonim oy: her deneme oturum satırı yarattığı için denemeler de sınırlanır.
VOTE_ATTEMPT_IP = Limit("vote-try-ip", 60, timedelta(hours=1))
# Aynı IP'den aynı ankete en çok 5 anonim oy (ortak ağlar için kasıtlı olarak cömert).
VOTE_POLL_IP = Limit("vote-ip", 5, timedelta(hours=24))
