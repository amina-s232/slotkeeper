from datetime import UTC, datetime, time, timedelta

import psycopg.errors
import pytest
from django.db import OperationalError

from apps.accounts.models import Role
from apps.scheduling.models import Appointment, AppointmentStatus, AvailabilityRule
from apps.scheduling.services.booking import (
    MAX_ATTEMPTS,
    ClientConflict,
    InvalidSlot,
    SlotUnavailable,
    book_appointment,
)
from apps.scheduling.services.lifecycle import (
    DeadlinePassed,
    InvalidTransition,
    cancel_appointment,
    complete_appointment,
    mark_no_show,
    reschedule_appointment,
)

pytestmark = pytest.mark.django_db

NOW = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)
NINE_IST = datetime(2030, 1, 7, 3, 30, tzinfo=UTC)  # Monday 09:00 in Asia/Kolkata
TEN_IST = NINE_IST + timedelta(hours=1)
AFTER_START = NINE_IST + timedelta(minutes=10)


@pytest.fixture
def provider(make_provider):
    provider = make_provider()  # cancel cut-off is 4 hours
    AvailabilityRule.objects.create(
        provider=provider, weekday=0, start_time=time(9), end_time=time(12)
    )
    return provider


@pytest.fixture
def alice(make_user):
    return make_user(email="alice@example.com")


@pytest.fixture
def bob(make_user):
    return make_user(email="bob@example.com")


@pytest.fixture
def booked(provider, alice):
    return book_appointment(client=alice, provider=provider, starts_at=NINE_IST, now=NOW)


def reload(appointment):
    return Appointment.objects.get(pk=appointment.pk)


# ---- cancel ----------------------------------------------------------------------------


def test_client_can_cancel_and_the_cancellation_is_recorded(booked, alice):
    cancel_appointment(appointment_id=booked.pk, actor=alice, now=NOW)
    booked = reload(booked)
    assert booked.status == AppointmentStatus.CANCELLED
    assert booked.cancelled_at == NOW
    assert booked.cancelled_by == alice


def test_a_cancelled_slot_can_be_booked_by_someone_else(provider, booked, alice, bob):
    cancel_appointment(appointment_id=booked.pk, actor=alice, now=NOW)
    again = book_appointment(client=bob, provider=provider, starts_at=NINE_IST, now=NOW)
    assert again.pk != booked.pk


def test_client_cannot_cancel_inside_the_cutoff(booked, alice):
    with pytest.raises(DeadlinePassed):
        cancel_appointment(appointment_id=booked.pk, actor=alice, now=NINE_IST - timedelta(hours=3))
    assert reload(booked).status == AppointmentStatus.BOOKED


def test_client_can_cancel_exactly_at_the_cutoff(booked, alice):
    cancel_appointment(appointment_id=booked.pk, actor=alice, now=NINE_IST - timedelta(hours=4))
    assert reload(booked).status == AppointmentStatus.CANCELLED


def test_one_second_past_the_cutoff_is_too_late(booked, alice):
    too_late = NINE_IST - timedelta(hours=4) + timedelta(seconds=1)
    with pytest.raises(DeadlinePassed):
        cancel_appointment(appointment_id=booked.pk, actor=alice, now=too_late)


def test_provider_can_cancel_inside_the_cutoff(provider, booked):
    cancel_appointment(
        appointment_id=booked.pk, actor=provider.user, now=NINE_IST - timedelta(hours=1)
    )
    assert reload(booked).status == AppointmentStatus.CANCELLED


def test_cancelling_twice_is_an_error(booked, alice):
    cancel_appointment(appointment_id=booked.pk, actor=alice, now=NOW)
    with pytest.raises(InvalidTransition):
        cancel_appointment(appointment_id=booked.pk, actor=alice, now=NOW)


def test_an_appointment_that_has_started_cannot_be_cancelled(provider, booked):
    with pytest.raises(InvalidTransition):
        cancel_appointment(appointment_id=booked.pk, actor=provider.user, now=AFTER_START)


@pytest.mark.parametrize("final", [AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW])
def test_a_finished_appointment_cannot_be_cancelled(provider, booked, final):
    Appointment.objects.filter(pk=booked.pk).update(status=final)
    with pytest.raises(InvalidTransition):
        cancel_appointment(appointment_id=booked.pk, actor=provider.user, now=NOW)


def test_admin_is_not_limited_by_the_cutoff(booked, make_user):
    admin = make_user(email="admin@example.com", role=Role.ADMIN)
    cancel_appointment(appointment_id=booked.pk, actor=admin, now=NINE_IST - timedelta(minutes=30))
    assert reload(booked).status == AppointmentStatus.CANCELLED


# ---- complete and no-show --------------------------------------------------------------


def test_started_appointment_can_be_completed(booked):
    complete_appointment(appointment_id=booked.pk, now=AFTER_START)
    assert reload(booked).status == AppointmentStatus.COMPLETED


def test_started_appointment_can_be_marked_no_show(booked):
    mark_no_show(appointment_id=booked.pk, now=AFTER_START)
    assert reload(booked).status == AppointmentStatus.NO_SHOW


@pytest.mark.parametrize("action", [complete_appointment, mark_no_show])
def test_cannot_finish_an_appointment_that_has_not_started(booked, action):
    with pytest.raises(InvalidTransition):
        action(appointment_id=booked.pk, now=NOW)
    assert reload(booked).status == AppointmentStatus.BOOKED


@pytest.mark.parametrize("action", [complete_appointment, mark_no_show])
def test_cannot_finish_a_cancelled_appointment(booked, alice, action):
    cancel_appointment(appointment_id=booked.pk, actor=alice, now=NOW)
    with pytest.raises(InvalidTransition):
        action(appointment_id=booked.pk, now=AFTER_START)


def test_completed_is_final(booked):
    complete_appointment(appointment_id=booked.pk, now=AFTER_START)
    with pytest.raises(InvalidTransition):
        mark_no_show(appointment_id=booked.pk, now=AFTER_START)
    assert reload(booked).status == AppointmentStatus.COMPLETED


# ---- reschedule ------------------------------------------------------------------------


def test_reschedule_moves_the_same_appointment(booked, alice):
    moved = reschedule_appointment(
        appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=NOW
    )
    assert moved.pk == booked.pk
    booked = reload(booked)
    assert booked.starts_at == TEN_IST
    assert booked.ends_at == TEN_IST + timedelta(minutes=30)
    assert booked.status == AppointmentStatus.BOOKED


def test_reschedule_frees_the_old_slot(provider, booked, alice, bob):
    reschedule_appointment(appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=NOW)
    taken = book_appointment(client=bob, provider=provider, starts_at=NINE_IST, now=NOW)
    assert taken.starts_at == NINE_IST


def test_reschedule_resets_the_reminder_so_the_new_time_gets_one(booked, alice):
    Appointment.objects.filter(pk=booked.pk).update(reminder_sent_at=NOW)
    reschedule_appointment(appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=NOW)
    assert reload(booked).reminder_sent_at is None


def test_reschedule_onto_a_taken_slot_conflicts_and_changes_nothing(provider, booked, alice, bob):
    book_appointment(client=bob, provider=provider, starts_at=TEN_IST, now=NOW)
    with pytest.raises(SlotUnavailable):
        reschedule_appointment(
            appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=NOW
        )
    assert reload(booked).starts_at == NINE_IST


def test_reschedule_cannot_double_book_the_client_elsewhere(provider, make_provider, booked, alice):
    other = make_provider()
    AvailabilityRule.objects.create(
        provider=other, weekday=0, start_time=time(9), end_time=time(12)
    )
    book_appointment(client=alice, provider=other, starts_at=TEN_IST, now=NOW)
    with pytest.raises(ClientConflict):
        reschedule_appointment(
            appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=NOW
        )
    assert reload(booked).starts_at == NINE_IST


@pytest.mark.parametrize(
    "target",
    [
        NINE_IST,  # where it already is
        NINE_IST + timedelta(minutes=15),  # off the grid
        NINE_IST + timedelta(days=1),  # Tuesday: no working hours
        NINE_IST + timedelta(hours=8),  # after hours
    ],
)
def test_reschedule_to_a_time_the_provider_does_not_offer_is_rejected(booked, alice, target):
    with pytest.raises(InvalidSlot):
        reschedule_appointment(appointment_id=booked.pk, actor=alice, new_starts_at=target, now=NOW)
    assert reload(booked).starts_at == NINE_IST


def test_reschedule_rejects_a_timestamp_without_an_offset(booked, alice):
    with pytest.raises(InvalidSlot):
        reschedule_appointment(
            appointment_id=booked.pk,
            actor=alice,
            new_starts_at=datetime(2030, 1, 7, 10, 0),
            now=NOW,
        )


def test_client_cannot_reschedule_inside_the_cutoff_but_provider_can(provider, booked, alice):
    late = NINE_IST - timedelta(hours=2)
    with pytest.raises(DeadlinePassed):
        reschedule_appointment(
            appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=late
        )
    reschedule_appointment(
        appointment_id=booked.pk, actor=provider.user, new_starts_at=TEN_IST, now=late
    )
    assert reload(booked).starts_at == TEN_IST


def test_cannot_reschedule_a_cancelled_appointment(booked, alice):
    cancel_appointment(appointment_id=booked.pk, actor=alice, now=NOW)
    with pytest.raises(InvalidTransition):
        reschedule_appointment(
            appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=NOW
        )


# ---- deadlock handling (simulated at the database call, as in test_booking) --------------


def _deadlock():
    error = OperationalError("deadlock detected")
    error.__cause__ = psycopg.errors.DeadlockDetected("deadlock detected")
    return error


def test_reschedule_retries_after_a_deadlock(booked, alice, monkeypatch):
    real_save = Appointment.save
    calls = []

    def flaky_save(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise _deadlock()
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(Appointment, "save", flaky_save)
    reschedule_appointment(appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=NOW)
    assert len(calls) == 2
    assert reload(booked).starts_at == TEN_IST


def test_reschedule_gives_up_after_max_attempts(booked, alice, monkeypatch):
    calls = []

    def always_deadlocks(self, *args, **kwargs):
        calls.append(1)
        raise _deadlock()

    monkeypatch.setattr(Appointment, "save", always_deadlocks)
    with pytest.raises(OperationalError):
        reschedule_appointment(
            appointment_id=booked.pk, actor=alice, new_starts_at=TEN_IST, now=NOW
        )
    assert len(calls) == MAX_ATTEMPTS
