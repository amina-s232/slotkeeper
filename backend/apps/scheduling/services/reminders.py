"""Reminder emails, safe to run from several workers at once.

Each appointment is handled in its own short transaction:

    lock one due appointment  ->  send its email  ->  stamp reminder_sent_at  ->  commit

`select_for_update(skip_locked=True)` is the key. A second worker does not wait behind the first
and does not pick the same row: it simply skips rows that are locked and takes the next one. So
N workers share the queue with no duplicates and no blocking.

Delivery guarantee: at least once. If the process dies after the email is sent but before the
commit, the row is still unstamped and the reminder goes out again next run. A duplicate reminder
is far better than a missed one. Exactly-once would need an outbox table; that is a later topic.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.scheduling.models import Appointment, AppointmentStatus

logger = logging.getLogger(__name__)


def _due(now: datetime, hours: int):
    return Appointment.objects.filter(
        status=AppointmentStatus.BOOKED,
        reminder_sent_at__isnull=True,
        starts_at__gt=now,
        starts_at__lte=now + timedelta(hours=hours),
    )


def _send(appointment: Appointment) -> None:
    local = appointment.starts_at.astimezone(ZoneInfo(appointment.provider.timezone))
    send_mail(
        subject=f"Reminder: your appointment with {appointment.provider.display_name}",
        message=(
            f"Hello {appointment.client.full_name},\n\n"
            f"This is a reminder of your appointment with {appointment.provider.display_name} "
            f"on {local:%A %d %B %Y} at {local:%H:%M} ({appointment.provider.timezone}).\n"
        ),
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=[appointment.client.email],
    )


def send_due_reminders(*, now: datetime | None = None, hours: int = 24) -> int:
    """Send every reminder due within `hours`. Returns how many were sent."""
    now = now or timezone.now()
    sent = 0
    failed: list[int] = []  # a row that keeps failing must not be picked forever
    while True:
        with transaction.atomic():
            appointment = (
                _due(now, hours)
                .exclude(pk__in=failed)
                .select_related("provider", "client")
                .select_for_update(skip_locked=True, of=("self",))
                .order_by("starts_at")
                .first()
            )
            if appointment is None:
                return sent
            try:
                _send(appointment)
            except Exception:  # one bad address must not stop everyone else's reminder
                logger.exception("Reminder failed for appointment %s", appointment.pk)
                failed.append(appointment.pk)
                continue
            appointment.reminder_sent_at = now
            appointment.save(update_fields=["reminder_sent_at", "updated_at"])
            sent += 1
