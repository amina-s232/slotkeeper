from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from apps.scheduling.models import Appointment, AppointmentStatus, Provider


@dataclass(frozen=True)
class Slot:
    start: datetime  # timezone-aware, UTC
    end: datetime


def cut_window(start: datetime, end: datetime, minutes: int) -> list[Slot]:
    """Split [start, end) into back-to-back slots; a partial slot at the end is dropped."""
    step = timedelta(minutes=minutes)
    slots = []
    cursor = start
    while cursor + step <= end:
        slots.append(Slot(cursor, cursor + step))
        cursor += step
    return slots


def _local_to_utc(day: date, at: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, at, tzinfo=tz).astimezone(UTC)


def _overlaps(slot: Slot, start: datetime, end: datetime) -> bool:
    return slot.start < end and slot.end > start


def candidate_slots(provider: Provider, day: date, now: datetime | None = None) -> list[Slot]:
    """Slots the provider offers on `day` (a date in the provider's own timezone)."""
    now = now or timezone.now()
    tz = ZoneInfo(provider.timezone)

    rules = (
        provider.rules.filter(weekday=day.weekday())
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=day))
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
    )  # query 1
    slots: list[Slot] = []
    for rule in rules:
        window_start = _local_to_utc(day, rule.start_time, tz)
        window_end = _local_to_utc(day, rule.end_time, tz)
        slots.extend(cut_window(window_start, window_end, provider.slot_minutes))
    if not slots:
        return []

    day_start = _local_to_utc(day, time.min, tz)
    day_end = _local_to_utc(day + timedelta(days=1), time.min, tz)
    time_off = list(  # query 2
        provider.time_off.filter(starts_at__lt=day_end, ends_at__gt=day_start)
    )

    earliest = now + timedelta(hours=provider.min_notice_hours)
    latest = now + timedelta(days=provider.booking_window_days)
    offered = {
        s
        for s in slots  # a set: overlapping rules cannot produce duplicate slots
        if earliest <= s.start <= latest
        and not any(_overlaps(s, t.starts_at, t.ends_at) for t in time_off)
    }
    return sorted(offered, key=lambda s: s.start)


def free_slots(provider: Provider, day: date, now: datetime | None = None) -> list[Slot]:
    """Candidate slots that are not already booked. Three queries total, however many slots."""
    candidates = candidate_slots(provider, day, now)
    if not candidates:
        return []
    booked = list(
        Appointment.objects.filter(
            provider=provider,
            status=AppointmentStatus.BOOKED,
            starts_at__lt=candidates[-1].end,
            ends_at__gt=candidates[0].start,
        ).values_list("starts_at", "ends_at")
    )  # query 3
    return [s for s in candidates if not any(_overlaps(s, b0, b1) for b0, b1 in booked)]
