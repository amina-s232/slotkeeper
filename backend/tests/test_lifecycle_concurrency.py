"""Races between lifecycle operations. Built like test_concurrency.py: warm threads, a Barrier,
many rounds, and every unexpected exception reported by name (a deadlock shows up as
'OperationalError'). Real commits are needed, hence transaction=True."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta

import pytest
from django.db import connection

from apps.scheduling.models import Appointment, AppointmentStatus, AvailabilityRule
from apps.scheduling.services.booking import SlotUnavailable, book_appointment
from apps.scheduling.services.lifecycle import (
    InvalidTransition,
    cancel_appointment,
    complete_appointment,
    mark_no_show,
    reschedule_appointment,
)

NOW = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)
FIRST_MONDAY = datetime(2030, 1, 7, 3, 30, tzinfo=UTC)  # 09:00 in Asia/Kolkata
TARGET = FIRST_MONDAY + timedelta(hours=1)  # 10:00, the slot everybody wants
CONTENDERS = 12
ROUNDS = 120  # measured: with the provider lock removed, 40 rounds caught it in
# 2 of 3 runs, 120 rounds in 5 of 5. A race test that misses a bug sometimes is not a guard.


def _close(barrier):
    barrier.wait(timeout=30)
    connection.close()


def _run_rounds(pool, make_tasks, check, reset):
    for round_number in range(ROUNDS):
        reset()
        barrier = threading.Barrier(len(make_tasks))
        futures = [pool.submit(task, barrier) for task in make_tasks]
        check(round_number, [future.result() for future in futures])


def _shutdown(pool, workers):
    closing = threading.Barrier(workers)
    for future in [pool.submit(_close, closing) for _ in range(workers)]:
        future.result()


@pytest.mark.django_db(transaction=True)
def test_many_clients_rescheduling_into_one_slot_exactly_one_wins(make_provider, make_user):
    provider = make_provider(booking_window_days=365)
    AvailabilityRule.objects.create(
        provider=provider, weekday=0, start_time=time(9), end_time=time(12)
    )
    clients = [make_user(email=f"c{i}@example.com") for i in range(CONTENDERS)]
    # Each client holds a 09:00 slot on a different Monday, and all want the same 10:00 slot.
    mine = [
        book_appointment(
            client=client,
            provider=provider,
            starts_at=FIRST_MONDAY + timedelta(weeks=i + 1),
            now=NOW,
        )
        for i, client in enumerate(clients)
    ]
    originals = {a.pk: (a.starts_at, a.ends_at) for a in mine}

    def reset():
        for pk, (start, end) in originals.items():
            Appointment.objects.filter(pk=pk).update(starts_at=start, ends_at=end)

    def attempt(appointment, client):
        def run(barrier):
            try:
                connection.ensure_connection()
                barrier.wait(timeout=30)
                reschedule_appointment(
                    appointment_id=appointment.pk, actor=client, new_starts_at=TARGET, now=NOW
                )
                return "won"
            except SlotUnavailable:
                return "conflict"
            except Exception as exc:
                return type(exc).__name__

        return run

    def check(round_number, results):
        assert results.count("won") == 1, (round_number, results)
        assert results.count("conflict") == CONTENDERS - 1, (round_number, results)

    with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
        try:
            tasks = [attempt(a, c) for a, c in zip(mine, clients, strict=True)]
            _run_rounds(pool, tasks, check, reset)
        finally:
            _shutdown(pool, CONTENDERS)


@pytest.mark.django_db(transaction=True)
def test_cancel_racing_reschedule_never_errors_or_corrupts(make_provider, make_user):
    provider = make_provider()
    AvailabilityRule.objects.create(
        provider=provider, weekday=0, start_time=time(9), end_time=time(12)
    )
    client = make_user(email="solo@example.com")
    appointment = book_appointment(
        client=client, provider=provider, starts_at=FIRST_MONDAY, now=NOW
    )

    def reset():
        Appointment.objects.filter(pk=appointment.pk).update(
            status=AppointmentStatus.BOOKED,
            starts_at=FIRST_MONDAY,
            ends_at=FIRST_MONDAY + timedelta(minutes=30),
            cancelled_at=None,
            cancelled_by=None,
        )

    def cancel(barrier):
        try:
            connection.ensure_connection()
            barrier.wait(timeout=30)
            cancel_appointment(appointment_id=appointment.pk, actor=client, now=NOW)
            return "cancelled"
        except InvalidTransition:
            return "too late"
        except Exception as exc:
            return type(exc).__name__

    def move(barrier):
        try:
            connection.ensure_connection()
            barrier.wait(timeout=30)
            reschedule_appointment(
                appointment_id=appointment.pk, actor=client, new_starts_at=TARGET, now=NOW
            )
            return "moved"
        except InvalidTransition:
            return "too late"
        except Exception as exc:
            return type(exc).__name__

    def check(round_number, results):
        cancelled, moved = results
        # Whichever order the database picks, the outcomes must make sense together:
        #   reschedule then cancel  -> ("cancelled", "moved")
        #   cancel then reschedule  -> ("cancelled", "too late")
        assert cancelled == "cancelled", (round_number, results)
        assert moved in ("moved", "too late"), (round_number, results)
        final = Appointment.objects.get(pk=appointment.pk)
        assert final.status == AppointmentStatus.CANCELLED, (round_number, results)

    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            _run_rounds(pool, [cancel, move], check, reset)
        finally:
            _shutdown(pool, 2)


@pytest.mark.django_db(transaction=True)
def test_complete_racing_no_show_exactly_one_wins(make_provider, make_user):
    """Without the appointment lock both would read 'booked', both would write, and both
    callers would be told they succeeded while the later write silently overwrote the earlier."""
    provider = make_provider()
    AvailabilityRule.objects.create(
        provider=provider, weekday=0, start_time=time(9), end_time=time(12)
    )
    client = make_user(email="solo@example.com")
    appointment = book_appointment(
        client=client, provider=provider, starts_at=FIRST_MONDAY, now=NOW
    )
    after_start = FIRST_MONDAY + timedelta(minutes=10)

    def reset():
        Appointment.objects.filter(pk=appointment.pk).update(status=AppointmentStatus.BOOKED)

    def attempt(action, label):
        def run(barrier):
            try:
                connection.ensure_connection()
                barrier.wait(timeout=30)
                action(appointment_id=appointment.pk, now=after_start)
                return label
            except InvalidTransition:
                return "refused"
            except Exception as exc:
                return type(exc).__name__

        return run

    def check(round_number, results):
        winners = [r for r in results if r != "refused"]
        assert len(winners) == 1, (round_number, results)
        final = Appointment.objects.get(pk=appointment.pk).status
        expected = (
            AppointmentStatus.COMPLETED if winners[0] == "completed" else AppointmentStatus.NO_SHOW
        )
        assert final == expected, (round_number, results, final)

    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            tasks = [attempt(complete_appointment, "completed"), attempt(mark_no_show, "no-show")]
            _run_rounds(pool, tasks, check, reset)
        finally:
            _shutdown(pool, 2)
