"""Everything that happens to an appointment after it has been booked.

Locking rule (the reason this module cannot deadlock with itself or with booking):
    1. Lock the APPOINTMENT row first.
    2. Only then, if the operation needs it, lock the PROVIDER row.
Every code path takes locks in that order, never the reverse, so two transactions can never each
hold the lock the other one is waiting for. `book_appointment` only ever takes the provider lock,
so it fits the same order.

Cancel, complete and no-show change one row and touch no time range, so the appointment lock is
all they need. Reschedule moves an appointment in time, so it also needs the provider lock (the
same one booking uses) and is protected by the same two exclusion constraints.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.scheduling.models import Appointment, AppointmentStatus, Provider
from apps.scheduling.services.booking import (
    CLIENT_OVERLAP_CONSTRAINT,
    MAX_ATTEMPTS,
    PROVIDER_OVERLAP_CONSTRAINT,
    BookingError,
    ClientConflict,
    InvalidSlot,
    SlotUnavailable,
    _is_deadlock,
    _violated_constraint,
)
from apps.scheduling.services.slots import candidate_slots

class InvalidTransition(BookingError):
    """The appointment is not in a state that allows this (maps to HTTP 409)."""


class DeadlinePassed(BookingError):
    """Clients can no longer change this appointment; contact the provider (maps to HTTP 409)."""


def _lock_appointment(appointment_id: int) -> Appointment:
    """Step 1 of the locking rule. `of=("self",)` locks only this table's row."""
    return Appointment.objects.select_for_update(of=("self",)).get(pk=appointment_id)


def _require_booked(appointment: Appointment, verb: str) -> None:
    if appointment.status != AppointmentStatus.BOOKED:
        raise InvalidTransition(
            f"A {appointment.get_status_display().lower()} appointment cannot be {verb}."
        )


def _require_not_started(appointment: Appointment, now: datetime) -> None:
    if appointment.starts_at <= now:
        raise InvalidTransition("This appointment has already started.")


def _enforce_client_deadline(appointment: Appointment, actor, now: datetime) -> None:
    """Clients must act before the provider's cut-off. Providers and admins are not limited."""
    if actor.role != Role.CLIENT:
        return
    hours = appointment.provider.cancel_cutoff_hours
    if now > appointment.starts_at - timedelta(hours=hours):
        raise DeadlinePassed(
            f"Changes are not allowed within {hours} hours of the start. Contact the provider."
        )


def cancel_appointment(*, appointment_id: int, actor, now: datetime | None = None) -> Appointment:
    now = now or timezone.now()
    with transaction.atomic():
        appointment = _lock_appointment(appointment_id)
        _require_booked(appointment, "cancelled")
        _require_not_started(appointment, now)
        _enforce_client_deadline(appointment, actor, now)
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_at = now
        appointment.cancelled_by = actor
        appointment.save(update_fields=["status", "cancelled_at", "cancelled_by", "updated_at"])
    return appointment


def _finish(appointment_id: int, new_status: str, verb: str, now: datetime | None) -> Appointment:
    now = now or timezone.now()
    with transaction.atomic():
        appointment = _lock_appointment(appointment_id)
        _require_booked(appointment, verb)
        if appointment.starts_at > now:
            raise InvalidTransition("This appointment has not started yet.")
        appointment.status = new_status
        appointment.save(update_fields=["status", "updated_at"])
    return appointment


def complete_appointment(*, appointment_id: int, now: datetime | None = None) -> Appointment:
    return _finish(appointment_id, AppointmentStatus.COMPLETED, "completed", now)


def mark_no_show(*, appointment_id: int, now: datetime | None = None) -> Appointment:
    return _finish(appointment_id, AppointmentStatus.NO_SHOW, "marked as a no-show", now)

def _run_with_retries(operation):
    """Run `operation` in a transaction, translating database errors into domain errors.

    Same safety net as booking: a deadlock aborts the transaction, so trying again is safe.
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            with transaction.atomic():
                return operation()
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
            if not _is_deadlock(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


def reschedule_appointment(
    *, appointment_id: int, actor, new_starts_at: datetime, now: datetime | None = None
) -> Appointment:
    """Move a booked appointment to another slot of the SAME provider.

    The row is updated in place (same id, same history). The exclusion constraints judge the new
    time exactly as they judge a new booking, so a taken slot fails cleanly.
    """
    if timezone.is_naive(new_starts_at):
        raise InvalidSlot("starts_at must include a timezone offset.")
    now = now or timezone.now()
    new_start = new_starts_at.astimezone(UTC)

    def operation() -> Appointment:
        appointment = _lock_appointment(appointment_id)  # lock 1: the appointment
        _require_booked(appointment, "rescheduled")
        _require_not_started(appointment, now)
        _enforce_client_deadline(appointment, actor, now)
        provider = Provider.objects.select_for_update(no_key=True).get(  # lock 2: the provider
            pk=appointment.provider_id
        )
        if not provider.is_active:
            raise InvalidSlot("This provider is not accepting bookings.")
        if new_start == appointment.starts_at:
            raise InvalidSlot("The appointment is already at that time.")
        local_day = new_start.astimezone(ZoneInfo(provider.timezone)).date()
        offered = {slot.start: slot for slot in candidate_slots(provider, local_day, now)}
        slot = offered.get(new_start)
        if slot is None:
            raise InvalidSlot("That time is not an available slot for this provider.")
        appointment.starts_at = slot.start
        appointment.ends_at = slot.end
        appointment.reminder_sent_at = None  # the new time deserves its own reminder
        appointment.save(update_fields=["starts_at", "ends_at", "reminder_sent_at", "updated_at"])
        return appointment

    return _run_with_retries(operation)
