"""The headline guarantee: many simultaneous requests, exactly one booking, and no errors.

Why this test is built the way it is (each point is a mistake I made or nearly made):
* transaction=True: threads open their own database connections, so the test data must be
  really committed. The default rolled-back-at-the-end test transaction is invisible to them.
* Warm, reused threads. An earlier version opened a fresh connection inside every thread. That
  staggered them by milliseconds, and a real deadlock bug slipped straight through: it passed
  20 runs out of 20. Here the pool lives for all rounds and each thread connects BEFORE the
  barrier, so the inserts really do collide.
* Many rounds in one test. The bug this catches shows up in roughly 1 round in 10, so a single
  round, or even 20 separate tests, would usually pass on broken code.
* A Barrier releases every thread at the same instant.
* Unexpected exceptions are reported by name, not hidden. "One winner" is not enough: the other
  nineteen must all be clean conflicts. A deadlock appears here as 'OperationalError'.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time

import pytest
from django.db import connection

from apps.scheduling.models import Appointment, AvailabilityRule
from apps.scheduling.services.booking import SlotUnavailable, book_appointment

NOW = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)
NINE_IST = datetime(2030, 1, 7, 3, 30, tzinfo=UTC)  # Monday 09:00 in Asia/Kolkata
CONTENDERS = 20
ROUNDS = 60


def _close_connection(barrier):
    barrier.wait(timeout=30)  # makes each pool thread take exactly one of these tasks
    connection.close()


@pytest.mark.django_db(transaction=True)
def test_only_one_of_many_concurrent_bookings_wins_every_round(make_provider, make_user):
    provider = make_provider()
    AvailabilityRule.objects.create(
        provider=provider, weekday=0, start_time=time(9), end_time=time(12)
    )
    clients = [make_user(email=f"client{i}@example.com") for i in range(CONTENDERS)]

    def attempt(client, barrier):
        try:
            connection.ensure_connection()  # connect first, so no thread is late to the barrier
            barrier.wait(timeout=30)
            book_appointment(client=client, provider=provider, starts_at=NINE_IST, now=NOW)
            return "won"
        except SlotUnavailable:
            return "conflict"
        except Exception as exc:  # report it; a bare crash would hide what actually happened
            return type(exc).__name__

    with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
        try:
            for round_number in range(ROUNDS):
                Appointment.objects.all().delete()  # free the slot again for the next round
                barrier = threading.Barrier(CONTENDERS)
                futures = [pool.submit(attempt, client, barrier) for client in clients]
                results = [future.result() for future in futures]
                assert results.count("won") == 1, (round_number, results)
                assert results.count("conflict") == CONTENDERS - 1, (round_number, results)
        finally:
            closing = threading.Barrier(CONTENDERS)
            for future in [pool.submit(_close_connection, closing) for _ in range(CONTENDERS)]:
                future.result()