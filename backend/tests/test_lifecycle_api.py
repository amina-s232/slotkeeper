from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.scheduling.services.booking import book_appointment
from tests.helpers import future_slot, open_all_week

pytestmark = pytest.mark.django_db

APPOINTMENTS = "/api/appointments/"


@pytest.fixture
def provider(make_provider):
    return open_all_week(make_provider())


@pytest.fixture
def alice(make_user):
    return make_user(email="alice@example.com")


@pytest.fixture
def bob(make_user):
    return make_user(email="bob@example.com")


@pytest.fixture
def booked(provider, alice):
    """Alice's appointment, 3 days ahead (outside the 4-hour cut-off)."""
    return book_appointment(client=alice, provider=provider, starts_at=future_slot(provider))


def url(appointment, action):
    return f"{APPOINTMENTS}{appointment.pk}/{action}/"


# ---- cancel ----------------------------------------------------------------------------


def test_client_cancels_their_own_appointment(booked, alice, auth_client):
    response = auth_client(alice).post(url(booked, "cancel"))
    assert response.status_code == 200
    assert response.data["status"] == "cancelled"
    assert response.data["cancelled_at"] is not None


def test_cancelled_slot_appears_in_the_slot_list_again(provider, booked, alice, auth_client):
    local_day = future_slot(provider).date()
    listing = f"/api/providers/{provider.id}/slots/?date={local_day}"
    taken = booked.starts_at.isoformat().replace("+00:00", "Z")
    before = [slot["starts_at"] for slot in auth_client(alice).get(listing).data]
    assert taken not in before
    auth_client(alice).post(url(booked, "cancel"))
    after = [slot["starts_at"] for slot in auth_client(alice).get(listing).data]
    assert taken in after


def test_cancel_inside_the_cutoff_is_409_for_a_client(provider, alice, auth_client):
    soon = timezone.now() + timedelta(hours=3)
    appointment = Appointment.objects.create(
        provider=provider, client=alice, starts_at=soon, ends_at=soon + timedelta(minutes=30)
    )
    response = auth_client(alice).post(url(appointment, "cancel"))
    assert response.status_code == 409
    assert response.data["detail"].code == "deadline_passed"


def test_cancelling_twice_is_409(booked, alice, auth_client):
    client = auth_client(alice)
    client.post(url(booked, "cancel"))
    response = client.post(url(booked, "cancel"))
    assert response.status_code == 409
    assert response.data["detail"].code == "invalid_transition"


def test_someone_elses_appointment_is_404_not_403(booked, bob, auth_client):
    assert auth_client(bob).post(url(booked, "cancel")).status_code == 404


def test_provider_can_cancel_an_appointment_with_them(provider, booked, auth_client):
    response = auth_client(provider.user).post(url(booked, "cancel"))
    assert response.status_code == 200


def test_a_different_provider_cannot_cancel_it(make_provider, booked, auth_client):
    other = make_provider()
    assert auth_client(other.user).post(url(booked, "cancel")).status_code == 404


def test_lifecycle_endpoints_require_login(booked, api_client):
    for action in ["cancel", "reschedule", "complete", "no-show"]:
        assert api_client.post(url(booked, action)).status_code == 401


# ---- reschedule ------------------------------------------------------------------------


def test_client_reschedules_to_another_slot(provider, booked, alice, auth_client):
    new_start = future_slot(provider, hour=10)
    response = auth_client(alice).post(
        url(booked, "reschedule"), {"starts_at": new_start.isoformat()}, format="json"
    )
    assert response.status_code == 200
    assert response.data["id"] == booked.pk
    booked.refresh_from_db()
    assert booked.starts_at == new_start


def test_reschedule_onto_a_taken_slot_is_409(provider, booked, alice, bob, auth_client):
    taken = future_slot(provider, hour=10)
    book_appointment(client=bob, provider=provider, starts_at=taken)
    response = auth_client(alice).post(
        url(booked, "reschedule"), {"starts_at": taken.isoformat()}, format="json"
    )
    assert response.status_code == 409
    assert response.data["detail"].code == "slot_unavailable"


def test_reschedule_to_a_time_not_offered_is_400(provider, booked, alice, auth_client):
    response = auth_client(alice).post(
        url(booked, "reschedule"),
        {"starts_at": future_slot(provider, hour=23).isoformat()},
        format="json",
    )
    assert response.status_code == 400


def test_reschedule_without_an_offset_is_400(provider, booked, alice, auth_client):
    naive = future_slot(provider, hour=10).replace(tzinfo=None).isoformat()
    response = auth_client(alice).post(
        url(booked, "reschedule"), {"starts_at": naive}, format="json"
    )
    assert response.status_code == 400


def test_reschedule_needs_starts_at(booked, alice, auth_client):
    assert auth_client(alice).post(url(booked, "reschedule"), {}, format="json").status_code == 400


# ---- complete and no-show --------------------------------------------------------------


@pytest.fixture
def started(provider, alice):
    """An appointment that began ten minutes ago."""
    start = timezone.now() - timedelta(minutes=10)
    return Appointment.objects.create(
        provider=provider, client=alice, starts_at=start, ends_at=start + timedelta(minutes=30)
    )


def test_provider_completes_a_started_appointment(provider, started, auth_client):
    response = auth_client(provider.user).post(url(started, "complete"))
    assert response.status_code == 200
    assert response.data["status"] == "completed"


def test_provider_marks_a_no_show(provider, started, auth_client):
    response = auth_client(provider.user).post(url(started, "no-show"))
    assert response.status_code == 200
    assert response.data["status"] == AppointmentStatus.NO_SHOW


def test_client_cannot_complete_their_own_appointment(started, alice, auth_client):
    assert auth_client(alice).post(url(started, "complete")).status_code == 403
    assert auth_client(alice).post(url(started, "no-show")).status_code == 403


def test_admin_can_complete_any_appointment(started, make_user, auth_client):
    admin = make_user(email="admin@example.com", role=Role.ADMIN)
    assert auth_client(admin).post(url(started, "complete")).status_code == 200


def test_completing_a_future_appointment_is_409(provider, booked, auth_client):
    response = auth_client(provider.user).post(url(booked, "complete"))
    assert response.status_code == 409
    assert response.data["detail"].code == "invalid_transition"
