"""Small helpers for API tests, which run against the real clock (no injected `now`)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.scheduling.models import AvailabilityRule


def open_all_week(provider, start=time(9), end=time(12)):
    """Give a provider the same working hours every day, so a slot always exists."""
    for weekday in range(7):
        AvailabilityRule.objects.create(
            provider=provider, weekday=weekday, start_time=start, end_time=end
        )
    return provider


def future_slot(provider, days_ahead=3, hour=9, minute=0):
    """An offered slot start (aware datetime) `days_ahead` days from now, in the provider's tz."""
    tz = ZoneInfo(provider.timezone)
    day = timezone.now().astimezone(tz).date() + timedelta(days=days_ahead)
    return datetime.combine(day, time(hour, minute), tzinfo=tz)
