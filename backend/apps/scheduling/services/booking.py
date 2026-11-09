from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.scheduling.models import Appointment, Provider
from apps.scheduling.services.slots import candidate_slots

PROVIDER_OVERLAP_CONSTRAINT = "no_overlapping_booked_appointments"
CLIENT_OVERLAP_CONSTRAINT = "client_cannot_double_book"


class BookingError(Exception):
    """Base class for every expected booking failure."""


class InvalidSlot(BookingError):
    """The requested time is not something this provider offers (maps to HTTP 400)."""


class SlotUnavailable(BookingError):
    """Someone else holds this provider at this time (maps to HTTP 409)."""


class ClientConflict(BookingError):
    """The client already has a booked appointment at this time (maps to HTTP 409)."""


def _violated_constraint(exc: IntegrityError) -> str | None:
    """Name of the database constraint behind an IntegrityError (psycopg 3 exposes it)."""
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def book_appointment(
    *,
    client,
    provider: Provider,
    starts_at: datetime,
    notes: str = "",
    now: datetime | None = None,
) -> Appointment:
    if timezone.is_naive(starts_at):
        raise InvalidSlot("starts_at must include a timezone offset.")
    if not provider.is_active:
        raise InvalidSlot("This provider is not accepting bookings.")

    starts_at = starts_at.astimezone(UTC)
    local_day = starts_at.astimezone(ZoneInfo(provider.timezone)).date()
    offered = {slot.start: slot for slot in candidate_slots(provider, local_day, now)}
    slot = offered.get(starts_at)
    if slot is None:
        raise InvalidSlot("That time is not an available slot for this provider.")

    try:
        with transaction.atomic():
            return Appointment.objects.create(
                provider=provider,
                client=client,
                starts_at=slot.start,
                ends_at=slot.end,
                notes=notes,
            )
    except IntegrityError as exc:
        constraint = _violated_constraint(exc)
        if constraint == PROVIDER_OVERLAP_CONSTRAINT:
            raise SlotUnavailable("That slot was just taken. Please pick another time.") from exc
        if constraint == CLIENT_OVERLAP_CONSTRAINT:
            raise ClientConflict("You already have an appointment at that time.") from exc
        raise
