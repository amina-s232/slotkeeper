import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time

import pytest
from django.db import connection

from apps.scheduling.models import Appointment, AppointmentStatus, AvailabilityRule
from apps.scheduling.services.booking import SlotUnavailable, book_appointment

NOW = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)
NINE_IST = datetime(2030, 1, 7, 3, 30, tzinfo=UTC)  # Monday 09:00 in Asia/Kolkata
CONTENDERS = 10


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("run", range(20))
def test_only_one_of_many_concurrent_bookings_wins(make_provider, make_user, run):
    provider = make_provider()
    AvailabilityRule.objects.create(
        provider=provider, weekday=0, start_time=time(9), end_time=time(12)
    )
    clients = [make_user(email=f"client{i}@example.com") for i in range(CONTENDERS)]
    barrier = threading.Barrier(CONTENDERS)

    def attempt(client):
        try:
            barrier.wait(timeout=15)
            book_appointment(client=client, provider=provider, starts_at=NINE_IST, now=NOW)
            return "won"
        except SlotUnavailable:
            return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
        results = list(pool.map(attempt, clients))

    assert results.count("won") == 1, results
    assert results.count("conflict") == CONTENDERS - 1, results
    booked = Appointment.objects.filter(provider=provider, status=AppointmentStatus.BOOKED)
    assert booked.count() == 1
