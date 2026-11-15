from django.contrib import admin

from .models import Appointment, AvailabilityRule, Provider, TimeOff


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["display_name", "specialty", "timezone", "is_active"]
    list_filter = ["is_active", "timezone"]
    search_fields = ["display_name", "user__email"]


@admin.register(AvailabilityRule)
class AvailabilityRuleAdmin(admin.ModelAdmin):
    list_display = ["provider", "weekday", "start_time", "end_time", "valid_from", "valid_to"]
    list_filter = ["weekday"]


@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ["provider", "starts_at", "ends_at", "reason"]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ["provider", "client", "starts_at", "status"]
    list_filter = ["status", "provider"]
    date_hierarchy = "starts_at"
    # Status changes must go through the API so the lifecycle rules apply; the admin only looks.
    readonly_fields = [
        "cancelled_at",
        "cancelled_by",
        "reminder_sent_at",
        "created_at",
        "updated_at",
    ]
