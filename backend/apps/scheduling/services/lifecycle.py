from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.scheduling.services.booking import BookingError


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
