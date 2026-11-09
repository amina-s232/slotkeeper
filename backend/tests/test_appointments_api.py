from datetime import UTC

import pytest

from apps.accounts.models import Role
from apps.scheduling.models import Appointment, AppointmentStatus
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


def booking(provider, start=None, **extra):
    start = start or future_slot(provider)
    return {"provider": provider.id, "starts_at": start.isoformat(), **extra}


# ---- booking ---------------------------------------------------------------------------


def test_client_can_book_a_slot(provider, alice, auth_client):
    response = auth_client(alice).post(
        APPOINTMENTS, booking(provider, notes="First visit"), format="json"
    )
    assert response.status_code == 201
    assert response.data["status"] == "booked"
    assert response.data["client"] == alice.id
    assert response.data["notes"] == "First visit"
    assert Appointment.objects.count() == 1


def test_booked_slot_disappears_from_the_slot_list(provider, alice, bob, auth_client):
    start = future_slot(provider)
    auth_client(alice).post(APPOINTMENTS, booking(provider, start), format="json")
    slots = (
        auth_client(bob)
        .get(f"/api/providers/{provider.id}/slots/", {"date": start.date().isoformat()})
        .data
    )
    assert len(slots) == 5


def test_second_booking_of_the_same_slot_is_409(provider, alice, bob, auth_client):
    auth_client(alice).post(APPOINTMENTS, booking(provider), format="json")
    response = auth_client(bob).post(APPOINTMENTS, booking(provider), format="json")
    assert response.status_code == 409
    assert response.data["detail"].code == "slot_unavailable"
    assert Appointment.objects.count() == 1


def test_client_cannot_book_two_providers_at_the_same_time(
    provider, make_provider, alice, auth_client
):
    other = open_all_week(make_provider())
    client = auth_client(alice)
    assert client.post(APPOINTMENTS, booking(provider), format="json").status_code == 201
    response = client.post(APPOINTMENTS, booking(other), format="json")
    assert response.status_code == 409
    assert response.data["detail"].code == "client_conflict"


def test_time_the_provider_does_not_offer_is_400(provider, alice, auth_client):
    response = auth_client(alice).post(
        APPOINTMENTS, booking(provider, future_slot(provider, hour=3)), format="json"
    )
    assert response.status_code == 400
    assert "starts_at" in response.data


def test_off_grid_time_is_400(provider, alice, auth_client):
    response = auth_client(alice).post(
        APPOINTMENTS, booking(provider, future_slot(provider, minute=10)), format="json"
    )
    assert response.status_code == 400


def test_timestamp_without_an_offset_is_rejected_not_guessed(provider, alice, auth_client):
    # The slot's UTC wall-clock time with the offset stripped. A lenient parser would read it
    # as UTC and *accept* it as a valid slot, so only a strict one returns 400 here.
    utc_wall_clock = future_slot(provider).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    naive = {"provider": provider.id, "starts_at": utc_wall_clock}
    response = auth_client(alice).post(APPOINTMENTS, naive, format="json")
    assert response.status_code == 400
    assert "starts_at" in response.data
    assert Appointment.objects.count() == 0


def test_unknown_or_inactive_provider_is_400(make_provider, alice, auth_client):
    inactive = open_all_week(make_provider(is_active=False))
    client = auth_client(alice)
    assert client.post(APPOINTMENTS, booking(inactive), format="json").status_code == 400
    bogus = {"provider": 999999, "starts_at": future_slot(inactive).isoformat()}
    assert client.post(APPOINTMENTS, bogus, format="json").status_code == 400


def test_only_clients_may_book(provider, make_user, auth_client, api_client):
    assert api_client.post(APPOINTMENTS, booking(provider), format="json").status_code == 401
    for role in (Role.PROVIDER, Role.ADMIN):
        user = make_user(email=f"{role}@example.com", role=role)
        response = auth_client(user).post(APPOINTMENTS, booking(provider), format="json")
        assert response.status_code == 403


# ---- who can see what ------------------------------------------------------------------


@pytest.fixture
def two_bookings(provider, make_provider, alice, bob):
    """Alice with `provider`, Bob with a different provider."""
    from apps.scheduling.services.booking import book_appointment

    other = open_all_week(make_provider())
    a = book_appointment(client=alice, provider=provider, starts_at=future_slot(provider))
    b = book_appointment(client=bob, provider=other, starts_at=future_slot(other))
    return a, b, other


def ids(response):
    return {row["id"] for row in response.data["results"]}


def test_client_sees_only_their_own_appointments(two_bookings, alice, auth_client):
    a, b, _ = two_bookings
    client = auth_client(alice)
    assert ids(client.get(APPOINTMENTS)) == {a.id}
    assert client.get(f"{APPOINTMENTS}{a.id}/").status_code == 200
    assert client.get(f"{APPOINTMENTS}{b.id}/").status_code == 404  # 404, not 403: no ID leak


def test_provider_sees_only_their_own_appointments(two_bookings, provider, auth_client):
    a, b, _ = two_bookings
    client = auth_client(provider.user)
    assert ids(client.get(APPOINTMENTS)) == {a.id}
    assert client.get(f"{APPOINTMENTS}{b.id}/").status_code == 404


def test_admin_sees_everything(two_bookings, make_user, auth_client):
    a, b, _ = two_bookings
    admin = make_user(email="admin@example.com", role=Role.ADMIN)
    assert ids(auth_client(admin).get(APPOINTMENTS)) == {a.id, b.id}


def test_list_can_be_filtered_by_status(provider, alice, auth_client):
    client = auth_client(alice)
    client.post(APPOINTMENTS, booking(provider), format="json")
    Appointment.objects.update(status=AppointmentStatus.CANCELLED)
    assert ids(client.get(APPOINTMENTS, {"status": "booked"})) == set()
    assert len(ids(client.get(APPOINTMENTS, {"status": "cancelled"}))) == 1


def test_appointments_require_login(api_client):
    assert api_client.get(APPOINTMENTS).status_code == 401
