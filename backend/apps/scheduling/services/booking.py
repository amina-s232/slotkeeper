"""Booking: the one place where appointments are created.

Design rule: this module *validates* that a time is something the provider offers, but it never
tries to decide whether the slot is already taken. That check-then-insert pattern is a race:
two requests can both see "free" and both insert. Instead we insert and let the PostgreSQL
exclusion constraints decide. Whoever commits first wins; everyone else gets an IntegrityError,
which we translate into a domain error.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.scheduling.models import Appointment, Provider
from apps.scheduling.services.slots import candidate_slots

PROVIDER_OVERLAP_CONSTRAINT = "no_overlapping_booked_appointments"
CLIENT_OVERLAP_CONSTRAINT = "client_cannot_double_book"
MAX_ATTEMPTS = 3  # tries per booking when PostgreSQL aborts a transaction for a deadlock


class BookingError(Exception):
    """Base class for every expected booking failure."""


class InvalidSlot(BookingError):
    """The requested time is not something this provider offers (maps to HTTP 400)."""


class SlotUnavailable(BookingError):
    """Someone else holds this provider at this time (maps to HTTP 409)."""


class ClientConflict(BookingError):
    """The client already has a booked appointment at this time (maps to HTTP 409)."""


def _is_deadlock(exc: OperationalError) -> bool:
    """True for PostgreSQL's 'deadlock detected' (SQLSTATE 40P01), as psycopg 3 reports it."""
    return getattr(exc.__cause__, "sqlstate", None) == "40P01"


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

    for attempt in range(MAX_ATTEMPTS):
        try:
            with transaction.atomic():
                # Queue bookings for this provider. The exclusion constraint still decides who
                # wins, but without this lock two inserts can each see the other's uncommitted
                # row while checking the constraint, wait on each other, and PostgreSQL aborts
                # one with "deadlock detected" (a 500 for the user). no_key=True does not clash
                # with the foreign-key checks that every insert performs.
                Provider.objects.select_for_update(no_key=True).get(pk=provider.pk)
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
                raise SlotUnavailable(
                    "That slot was just taken. Please pick another time."
                ) from exc
            if constraint == CLIENT_OVERLAP_CONSTRAINT:
                raise ClientConflict("You already have an appointment at that time.") from exc
            raise
        except OperationalError as exc:
            # The lock removes the common deadlock. This is the safety net for the rest (for
            # example one client booking two providers at the same instant). PostgreSQL has
            # already rolled this transaction back, so trying again is safe: the retry then
            # sees the winner's committed row and fails cleanly as a conflict.
            if not _is_deadlock(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
    raise AssertionError("unreachable")  # pragma: no cover
