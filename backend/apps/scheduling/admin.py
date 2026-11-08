from django.contrib import admin

from .models import Appointment, AvailabilityRule, Provider, TimeOff


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["display_name", "specialty", "timezone", "is_active"]


@admin.register(AvailabilityRule)
class AvailabilityRuleAdmin(admin.ModelAdmin):
    list_display = ["provider", "weekday", "start_time", "end_time"]


@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ["provider", "starts_at", "ends_at", "reason"]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ["provider", "client", "starts_at", "ends_at", "status"]
    list_filter = ["status", "provider"]
