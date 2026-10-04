from django import template
from django.utils import timezone
from django.utils.formats import date_format

register = template.Library()


@register.filter
def relative_time(value):
    seconds = int((timezone.now() - value).total_seconds())
    if seconds < 60:
        return "az önce"
    if seconds < 3600:
        return f"{seconds // 60} dakika önce"
    if seconds < 86400:
        return f"{seconds // 3600} saat önce"
    if seconds < 7 * 86400:
        return f"{seconds // 86400} gün önce"
    return date_format(timezone.localtime(value), "j F Y")
