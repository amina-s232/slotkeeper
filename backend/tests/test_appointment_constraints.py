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
def client_a(make_user):
    return make_user(email="a@example.com")


@pytest.fixture
def client_b(make_user):
    return make_user(email="b@example.com")


def book(provider, client, start, minutes=30, status=AppointmentStatus.BOOKED):
    return Appointment.objects.create(
        provider=provider,
        client=client,
        starts_at=start,
        ends_at=start + timedelta(minutes=minutes),
        status=status,
    )


# ---- one provider cannot be double-booked ----------------------------------------------
# Different clients are used on purpose, so only the provider constraint can be responsible.


def test_identical_slot_is_rejected(provider, client_a, client_b):
    book(provider, client_a, START)
    with pytest.raises(IntegrityError, match="no_overlapping_booked_appointments"):
        with transaction.atomic():
            book(provider, client_b, START)


def test_partial_overlap_is_rejected(provider, client_a, client_b):
    book(provider, client_a, START)
    with pytest.raises(IntegrityError, match="no_overlapping_booked_appointments"):
        with transaction.atomic():
            book(provider, client_b, START + timedelta(minutes=15))


def test_back_to_back_slots_are_allowed(provider, client_a, client_b):
    book(provider, client_a, START)
    book(provider, client_b, START + timedelta(minutes=30))
    assert Appointment.objects.count() == 2


def test_same_time_with_a_different_provider_is_allowed(
    provider, other_provider, client_a, client_b
):
    book(provider, client_a, START)
    book(other_provider, client_b, START)
    assert Appointment.objects.count() == 2


def test_cancelled_appointment_frees_the_slot(provider, client_a, client_b):
    first = book(provider, client_a, START)
    first.status = AppointmentStatus.CANCELLED
    first.save()
    book(provider, client_b, START)
    assert Appointment.objects.filter(status=AppointmentStatus.BOOKED).count() == 1


def test_end_must_be_after_start(provider, client_a):
    with pytest.raises(IntegrityError, match="appointment_ends_after_start"):
        with transaction.atomic():
            book(provider, client_a, START, minutes=-10)


# ---- one client cannot be in two places at once ----------------------------------------


def test_client_cannot_overlap_across_different_providers(provider, other_provider, client_a):
    book(provider, client_a, START)
    with pytest.raises(IntegrityError, match="client_cannot_double_book"):
        with transaction.atomic():
            book(other_provider, client_a, START + timedelta(minutes=15))


def test_client_can_book_back_to_back_with_different_providers(provider, other_provider, client_a):
    book(provider, client_a, START)
    book(other_provider, client_a, START + timedelta(minutes=30))
    assert Appointment.objects.count() == 2


def test_cancelling_frees_the_client_too(provider, other_provider, client_a):
    first = book(provider, client_a, START)
    first.status = AppointmentStatus.CANCELLED
    first.save()
    book(other_provider, client_a, START)
    assert Appointment.objects.filter(status=AppointmentStatus.BOOKED).count() == 1
