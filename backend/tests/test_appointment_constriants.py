from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import Role
from apps.scheduling.models import Appointment, AppointmentStatus, Provider

pytestmark = pytest.mark.django_db

START = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)


@pytest.fixture
def provider(make_user):
    user = make_user(email="doc@example.com", role=Role.PROVIDER)
    return Provider.objects.create(user=user, display_name="Dr Doc")


@pytest.fixture
def other_provider(make_user):
    user = make_user(email="doc2@example.com", role=Role.PROVIDER)
    return Provider.objects.create(user=user, display_name="Dr Two")


@pytest.fixture
def client_user(make_user):
    return make_user(email="client@example.com")


def book(provider, client, start, minutes=30, status=AppointmentStatus.BOOKED):
    return Appointment.objects.create(
        provider=provider,
        client=client,
        starts_at=start,
        ends_at=start + timedelta(minutes=minutes),
        status=status,
    )


def test_identical_slot_is_rejected(provider, client_user):
    book(provider, client_user, START)
    with pytest.raises(IntegrityError, match="no_overlapping_booked_appointments"):
        with transaction.atomic():
            book(provider, client_user, START)


def test_partial_overlap_is_rejected(provider, client_user):
    book(provider, client_user, START)
    with pytest.raises(IntegrityError, match="no_overlapping_booked_appointments"):
        with transaction.atomic():
            book(provider, client_user, START + timedelta(minutes=15))


def test_back_to_back_slots_are_allowed(provider, client_user):
    book(provider, client_user, START)
    book(provider, client_user, START + timedelta(minutes=30))
    assert Appointment.objects.count() == 2


def test_same_time_with_a_different_provider_is_allowed(provider, other_provider, client_user):
    book(provider, client_user, START)
    book(other_provider, client_user, START)
    assert Appointment.objects.count() == 2


def test_cancelled_appointment_frees_the_slot(provider, client_user):
    first = book(provider, client_user, START)
    first.status = AppointmentStatus.CANCELLED
    first.save()
    book(provider, client_user, START)
    assert Appointment.objects.filter(status=AppointmentStatus.BOOKED).count() == 1


def test_end_must_be_after_start(provider, client_user):
    with pytest.raises(IntegrityError, match="appointment_ends_after_start"):
        with transaction.atomic():
            book(provider, client_user, START, minutes=-10)
