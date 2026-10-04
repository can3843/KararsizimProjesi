from django.contrib import admin, messages
from django.db.models import Count

from .models import Option, Poll, Report, Vote


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0
    max_num = 5


class ReportInline(admin.TabularInline):
    model = Report
    extra = 0
    can_delete = False
    readonly_fields = ("reporter", "reason", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("question", "author", "status", "total_votes", "report_count", "created_at")
    list_filter = ("status",)
    actions = ["close_selected"]
    search_fields = ("question", "public_id", "author__username")
    readonly_fields = ("public_id", "total_votes", "created_at")
    list_select_related = ("author",)
    inlines = [OptionInline, ReportInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_report_count=Count("reports"))

    @admin.display(description="Bildirim", ordering="_report_count")
    def report_count(self, obj):
        return obj._report_count

    @admin.action(description="Seçili anketleri kapat")
    def close_selected(self, request, queryset):
        updated = queryset.update(status=Poll.Status.CLOSED)
        self.message_user(request, f"{updated} anket kapatıldı.", messages.SUCCESS)


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ("text", "poll", "position", "vote_count")
    list_select_related = ("poll",)


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("poll", "option", "user", "created_at")
    list_select_related = ("poll", "option", "user")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("poll", "reason", "reporter", "created_at")
    list_filter = ("reason",)
    list_select_related = ("poll", "reporter")
    readonly_fields = ("poll", "reporter", "reason", "created_at")

    def has_add_permission(self, request):
        return False
