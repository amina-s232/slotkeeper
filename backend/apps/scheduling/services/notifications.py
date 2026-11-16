"""Emails about what happened to an appointment (reminders live in reminders.py)."""

import logging
from zoneinfo import ZoneInfo

from django.core.mail import send_mail

from apps.scheduling.models import Appointment

logger = logging.getLogger(__name__)


def send_cancellation_notice(appointment: Appointment, cancelled_by) -> None:
    """Tell the OTHER side that an appointment was cancelled.

    Called from `transaction.on_commit`, so nothing is sent if the cancel is rolled back. A
    failing mail server must never turn a successful cancellation into an error, so failures are
    logged and swallowed.
    """
    provider = appointment.provider
    client = appointment.client
    if cancelled_by.pk == client.pk:
        recipient, who = provider.user, client.full_name
    else:  # the provider or an admin cancelled: the client needs to know
        recipient, who = client, provider.display_name
    local = appointment.starts_at.astimezone(ZoneInfo(provider.timezone))
    try:
        send_mail(
            subject=f"Appointment cancelled: {local:%d %b %Y, %H:%M}",
            message=(
                f"Hello {recipient.full_name},\n\n"
                f"{who} cancelled the appointment on {local:%A %d %B %Y} at {local:%H:%M} "
                f"({provider.timezone}).\n"
            ),
            from_email=None,
            recipient_list=[recipient.email],
        )
    except Exception:
        logger.exception("Cancellation notice failed for appointment %s", appointment.pk)
