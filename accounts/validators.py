from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

FORBIDDEN_USERNAMES = frozenset({
    "admin", "root", "api", "static", "anket",
    "giris", "kayit", "cikis", "kullanici", "hakkinda",
})

username_format_validator = RegexValidator(
    regex=r"^[a-zA-Z0-9_]{3,20}\Z",
    message="Kullanıcı adı 3–20 karakter olmalı; sadece harf, rakam ve alt çizgi kullanabilirsin.",
)


def validate_username_not_forbidden(value):
    if value.lower() in FORBIDDEN_USERNAMES:
        raise ValidationError("Bu kullanıcı adı kullanılamaz.", code="forbidden_username")
