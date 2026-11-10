from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg.errors
import pytest
from django.db import OperationalError

from apps.scheduling.models import (
    Appointment,
    AppointmentStatus,
    AvailabilityRule,
    TimeOff,
)
from apps.scheduling.services.booking import (
    MAX_ATTEMPTS,
    ClientConflict,
    InvalidSlot,
    SlotUnavailable,
    book_appointment,
)

pytestmark = pytest.mark.django_db

MONDAY = date(2030, 1, 7)
NOW = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)
NINE_IST = datetime(2030, 1, 7, 3, 30, tzinfo=UTC)  # 09:00 in Asia/Kolkata


@pytest.fixture
def provider(make_provider):
    provider = make_provider()  # Asia/Kolkata, 30-minute slots, 2h notice, 30-day window
    AvailabilityRule.objects.create(
        provider=provider, weekday=0, start_time=time(9), end_time=time(12)
    )
    return provider


@pytest.fixture
def client_a(make_user):
    return make_user(email="a@example.com")


@pytest.fixture
def client_b(make_user):
    return make_user(email="b@example.com")


def test_booking_a_free_slot_creates_a_booked_appointment(provider, client_a):
    appointment = book_appointment(
        client=client_a, provider=provider, starts_at=NINE_IST, notes="Check-up", now=NOW
    )
    assert appointment.pk
    assert appointment.status == AppointmentStatus.BOOKED
    assert appointment.starts_at == NINE_IST
    assert appointment.ends_at == NINE_IST + timedelta(minutes=30)
    assert appointment.notes == "Check-up"


def test_any_timezone_is_accepted_if_it_is_the_same_instant(provider, client_a):
    local = datetime(2030, 1, 7, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    appointment = book_appointment(client=client_a, provider=provider, starts_at=local, now=NOW)
    assert appointment.starts_at == NINE_IST


def test_naive_datetime_is_rejected(provider, client_a):
    with pytest.raises(InvalidSlot):
        book_appointment(
            client=client_a, provider=provider, starts_at=datetime(2030, 1, 7, 9, 0), now=NOW
        )


@pytest.mark.parametrize(
    "start",
    [
        NINE_IST + timedelta(minutes=15),  # off the 30-minute grid
        NINE_IST + timedelta(seconds=30),  # not on a whole minute
        NINE_IST - timedelta(hours=1),  # before working hours
        NINE_IST + timedelta(hours=8),  # after working hours
        NINE_IST + timedelta(days=1),  # Tuesday: no rule
    ],
)
def test_times_that_are_not_offered_are_rejected(provider, client_a, start):
    with pytest.raises(InvalidSlot):
        book_appointment(client=client_a, provider=provider, starts_at=start, now=NOW)
    assert Appointment.objects.count() == 0


def test_past_slot_is_rejected(provider, client_a):
    with pytest.raises(InvalidSlot):
        book_appointment(
            client=client_a,
            provider=provider,
            starts_at=NINE_IST,
            now=NINE_IST + timedelta(hours=1),
        )


def test_slot_inside_the_minimum_notice_is_rejected(provider, client_a):
    one_hour_before = NINE_IST - timedelta(hours=1)  # notice is 2 hours
    with pytest.raises(InvalidSlot):
        book_appointment(
            client=client_a, provider=provider, starts_at=NINE_IST, now=one_hour_before
        )


def test_slot_beyond_the_booking_window_is_rejected(provider, client_a):
    far_future = NINE_IST + timedelta(weeks=8)  # still a Monday, but > 30 days from NOW
    with pytest.raises(InvalidSlot):
        book_appointment(client=client_a, provider=provider, starts_at=far_future, now=NOW)


def test_inactive_provider_cannot_be_booked(provider, client_a):
    provider.is_active = False
    provider.save()
    with pytest.raises(InvalidSlot):
        book_appointment(client=client_a, provider=provider, starts_at=NINE_IST, now=NOW)


def test_time_off_blocks_booking(provider, client_a):
    TimeOff.objects.create(
        provider=provider,
        starts_at=NINE_IST - timedelta(hours=1),
        ends_at=NINE_IST + timedelta(hours=1),
    )
    with pytest.raises(InvalidSlot):
        book_appointment(client=client_a, provider=provider, starts_at=NINE_IST, now=NOW)


def test_second_booking_of_the_same_slot_is_a_conflict(provider, client_a, client_b):
    book_appointment(client=client_a, provider=provider, starts_at=NINE_IST, now=NOW)
    with pytest.raises(SlotUnavailable):
        book_appointment(client=client_b, provider=provider, starts_at=NINE_IST, now=NOW)
    assert Appointment.objects.filter(status=AppointmentStatus.BOOKED).count() == 1


def test_client_cannot_hold_two_overlapping_appointments(provider, make_provider, client_a):
    other = make_provider()
    AvailabilityRule.objects.create(
        provider=other, weekday=0, start_time=time(9), end_time=time(12)
    )
    book_appointment(client=client_a, provider=provider, starts_at=NINE_IST, now=NOW)
    with pytest.raises(ClientConflict):
        book_appointment(client=client_a, provider=other, starts_at=NINE_IST, now=NOW)


def test_cancelled_slot_can_be_booked_again(provider, client_a, client_b):
    first = book_appointment(client=client_a, provider=provider, starts_at=NINE_IST, now=NOW)
    first.status = AppointmentStatus.CANCELLED
    first.save()
    second = book_appointment(client=client_b, provider=provider, starts_at=NINE_IST, now=NOW)
    assert second.pk != first.pk


# ---- deadlock handling -----------------------------------------------------------------
# A real deadlock can't be forced on demand, so these simulate one at the database call.


def _deadlock():
    error = OperationalError("deadlock detected")
    error.__cause__ = psycopg.errors.DeadlockDetected("deadlock detected")
    return error


def test_a_deadlock_is_retried_and_the_booking_then_succeeds(provider, client_a, monkeypatch):
    real_create = Appointment.objects.create
    calls = []

    def flaky_create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise _deadlock()
        return real_create(**kwargs)

    monkeypatch.setattr(Appointment.objects, "create", flaky_create)
    appointment = book_appointment(client=client_a, provider=provider, starts_at=NINE_IST, now=NOW)
    assert appointment.pk
    assert len(calls) == 2


def test_a_persistent_deadlock_is_raised_not_hidden(provider, client_a, monkeypatch):
    calls = []

    def always_deadlocks(**kwargs):
        calls.append(kwargs)
        raise _deadlock()

    monkeypatch.setattr(Appointment.objects, "create", always_deadlocks)
    with pytest.raises(OperationalError):
        book_appointment(client=client_a, provider=provider, starts_at=NINE_IST, now=NOW)
    assert len(calls) == MAX_ATTEMPTS


def test_other_database_errors_are_not_retried(provider, client_a, monkeypatch):
    calls = []

    def connection_lost(**kwargs):
        calls.append(kwargs)
        raise OperationalError("connection lost")

    monkeypatch.setattr(Appointment.objects, "create", connection_lost)
    with pytest.raises(OperationalError):
        book_appointment(client=client_a, provider=provider, starts_at=NINE_IST, now=NOW)
    assert len(calls) == 1
