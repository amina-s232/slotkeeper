import threading
import time as clock
from datetime import UTC, datetime, timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.db import connection, transaction

from apps.scheduling import services
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.scheduling.services.reminders import send_due_reminders

pytestmark = pytest.mark.django_db

NOW = datetime(2030, 1, 7, 0, 0, tzinfo=UTC)


@pytest.fixture
def provider(make_provider):
    return make_provider()


def appointment(provider, make_user, n, hours_ahead, **extra):
    """One appointment for a fresh client, `hours_ahead` from NOW (plus n minutes to stay apart)."""
    client = make_user(email=f"client{n}@example.com")
    start = NOW + timedelta(hours=hours_ahead, minutes=n)
    return Appointment.objects.create(
        provider=provider,
        client=client,
        starts_at=start,
        ends_at=start + timedelta(minutes=1),
        **extra,
    )


def test_a_due_appointment_gets_one_reminder_and_is_stamped(provider, make_user):
    due = appointment(provider, make_user, 1, hours_ahead=5)
    assert send_due_reminders(now=NOW) == 1
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["client1@example.com"]
    assert provider.display_name in mail.outbox[0].subject
    due.refresh_from_db()
    assert due.reminder_sent_at == NOW


def test_running_again_sends_nothing_more(provider, make_user):
    appointment(provider, make_user, 1, hours_ahead=5)
    send_due_reminders(now=NOW)
    assert send_due_reminders(now=NOW) == 0
    assert len(mail.outbox) == 1


def test_the_email_shows_the_time_in_the_providers_timezone(provider, make_user):
    appointment(provider, make_user, 1, hours_ahead=5)  # 05:01 UTC = 10:31 in Asia/Kolkata
    send_due_reminders(now=NOW)
    assert "10:31" in mail.outbox[0].body
    assert "Asia/Kolkata" in mail.outbox[0].body


def test_only_appointments_inside_the_window_are_reminded(provider, make_user):
    appointment(provider, make_user, 1, hours_ahead=5)
    appointment(provider, make_user, 2, hours_ahead=30)  # beyond 24 hours
    assert send_due_reminders(now=NOW, hours=24) == 1
    assert send_due_reminders(now=NOW, hours=48) == 1  # the later one is now due


def test_past_and_inactive_appointments_are_never_reminded(provider, make_user):
    appointment(provider, make_user, 1, hours_ahead=-2)  # already started
    appointment(provider, make_user, 2, hours_ahead=5, status=AppointmentStatus.CANCELLED)
    appointment(provider, make_user, 3, hours_ahead=6, status=AppointmentStatus.COMPLETED)
    assert send_due_reminders(now=NOW) == 0
    assert mail.outbox == []


def test_one_failing_email_does_not_block_the_others(provider, make_user, monkeypatch):
    bad = appointment(provider, make_user, 1, hours_ahead=5)
    good = appointment(provider, make_user, 2, hours_ahead=6)
    real = services.reminders.send_mail

    def flaky(**kwargs):
        if kwargs["recipient_list"] == ["client1@example.com"]:
            raise RuntimeError("mailbox does not exist")
        return real(**kwargs)

    monkeypatch.setattr(services.reminders, "send_mail", flaky)
    assert send_due_reminders(now=NOW) == 1
    bad.refresh_from_db()
    good.refresh_from_db()
    assert bad.reminder_sent_at is None  # will be retried on the next run
    assert good.reminder_sent_at == NOW


def test_management_command_runs_and_reports(provider, make_user, capsys):
    appointment(provider, make_user, 1, hours_ahead=1)
    # The command uses the real clock, so only check that it runs and reports a count.
    call_command("send_reminders")
    assert "Sent" in capsys.readouterr().out


# ---- two workers at once ---------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_parallel_workers_send_every_reminder_exactly_once(provider, make_user, monkeypatch):
    total = 30
    for n in range(total):
        appointment(provider, make_user, n, hours_ahead=5)

    real = services.reminders.send_mail

    def slow_send(**kwargs):
        clock.sleep(0.01)  # widen the window in which two workers could grab the same row
        return real(**kwargs)

    monkeypatch.setattr(services.reminders, "send_mail", slow_send)

    results, errors = [], []
    start = threading.Barrier(3)

    def worker():
        try:
            connection.ensure_connection()
            start.wait(timeout=30)
            results.append(send_due_reminders(now=NOW))
        except Exception as exc:  # report, don't hide
            errors.append(repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    recipients = [m.to[0] for m in mail.outbox]
    assert len(recipients) == total, "a reminder was missed or duplicated"
    assert len(set(recipients)) == total, "someone was reminded twice"
    assert sum(results) == total
    assert Appointment.objects.filter(reminder_sent_at__isnull=True).count() == 0


@pytest.mark.django_db(transaction=True)
def test_a_worker_skips_rows_another_worker_holds_instead_of_waiting(provider, make_user):
    """This is what skip_locked buys: no queueing behind a busy worker."""
    appointment(provider, make_user, 1, hours_ahead=5)
    holding, release = threading.Event(), threading.Event()

    def hold_the_lock():
        try:
            with transaction.atomic():
                list(Appointment.objects.select_for_update())
                holding.set()
                release.wait(timeout=30)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_the_lock)
    holder.start()
    assert holding.wait(timeout=10)

    outcome = []

    def other_worker():
        try:
            outcome.append(send_due_reminders(now=NOW))
        finally:
            connection.close()

    worker = threading.Thread(target=other_worker)
    worker.start()
    worker.join(timeout=3)
    still_waiting = worker.is_alive()
    release.set()
    holder.join(timeout=10)
    worker.join(timeout=10)

    assert not still_waiting, "the second worker queued behind the lock instead of skipping it"
    assert outcome == [0]
    assert mail.outbox == []
