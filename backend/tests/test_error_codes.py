"""The `code` field must exist in the JSON a real client receives, not only on the exception.

These read `response.json()` (the rendered body), because `response.data` would still show the
Python object and hide exactly the bug this file exists to catch.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.scheduling.models import Appointment
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


def body(response):
    return response.json()


def test_cancelling_twice_returns_the_invalid_transition_code(provider, alice, auth_client):
    appointment = book_appointment(client=alice, provider=provider, starts_at=future_slot(provider))
    client = auth_client(alice)
    client.post(f"{APPOINTMENTS}{appointment.pk}/cancel/")
    response = client.post(f"{APPOINTMENTS}{appointment.pk}/cancel/")
    assert response.status_code == 409
    assert body(response)["code"] == "invalid_transition"
    assert "cancelled" in body(response)["detail"]


def test_cancelling_too_late_returns_the_deadline_code(provider, alice, auth_client):
    soon = timezone.now() + timedelta(hours=1)
    appointment = Appointment.objects.create(
        provider=provider, client=alice, starts_at=soon, ends_at=soon + timedelta(minutes=30)
    )
    response = auth_client(alice).post(f"{APPOINTMENTS}{appointment.pk}/cancel/")
    assert body(response)["code"] == "deadline_passed"


def test_booking_a_taken_slot_returns_the_slot_unavailable_code(provider, alice, bob, auth_client):
    start = future_slot(provider)
    book_appointment(client=alice, provider=provider, starts_at=start)
    response = auth_client(bob).post(
        APPOINTMENTS, {"provider": provider.id, "starts_at": start.isoformat()}, format="json"
    )
    assert response.status_code == 409
    assert body(response)["code"] == "slot_unavailable"


def test_booking_while_busy_elsewhere_returns_the_client_conflict_code(
    provider, make_provider, alice, auth_client
):
    other = open_all_week(make_provider())
    start = future_slot(provider)
    book_appointment(client=alice, provider=other, starts_at=start)
    response = auth_client(alice).post(
        APPOINTMENTS, {"provider": provider.id, "starts_at": start.isoformat()}, format="json"
    )
    assert body(response)["code"] == "client_conflict"


def test_common_http_errors_carry_codes_too(provider, alice, api_client, auth_client):
    assert body(api_client.get(APPOINTMENTS))["code"] == "not_authenticated"
    assert body(auth_client(alice).get(f"{APPOINTMENTS}999999/"))["code"] == "not_found"
    assert body(auth_client(alice).get("/api/me/provider/"))["code"] == "permission_denied"


def test_validation_errors_keep_their_field_shape(provider, alice, auth_client):
    response = auth_client(alice).post(APPOINTMENTS, {}, format="json")
    assert response.status_code == 400
    assert "provider" in body(response)
    assert "code" not in body(response)
