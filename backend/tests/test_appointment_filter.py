"""The date-range filter on /api/appointments/ and the provider timezone it needs."""

from datetime import UTC, datetime, timedelta

import pytest

from apps.scheduling.models import Appointment
from tests.helpers import open_all_week

pytestmark = pytest.mark.django_db

APPOINTMENTS = "/api/appointments/"
NOON = datetime(2030, 1, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def provider(make_provider):
    return open_all_week(make_provider())


@pytest.fixture
def alice(make_user):
    return make_user(email="alice@example.com")


def make_appointment(provider, client, start):
    return Appointment.objects.create(
        provider=provider, client=client, starts_at=start, ends_at=start + timedelta(minutes=30)
    )


# ---- date-range filter -----------------------------------------------------------------


def test_appointments_can_be_filtered_to_a_day(provider, alice, auth_client):
    inside = make_appointment(provider, alice, NOON)
    make_appointment(provider, alice, NOON + timedelta(days=1))
    make_appointment(provider, alice, NOON - timedelta(days=1))
    response = auth_client(alice).get(
        APPOINTMENTS,
        {"starts_after": "2030-01-07T00:00:00Z", "starts_before": "2030-01-08T00:00:00Z"},
    )
    assert response.status_code == 200
    assert [a["id"] for a in response.data["results"]] == [inside.pk]


def test_the_range_includes_its_start_and_excludes_its_end(provider, alice, auth_client):
    on_start = make_appointment(provider, alice, NOON)
    make_appointment(provider, alice, NOON + timedelta(hours=1))  # exactly on the end
    response = auth_client(alice).get(
        APPOINTMENTS,
        {
            "starts_after": NOON.isoformat(),
            "starts_before": (NOON + timedelta(hours=1)).isoformat(),
        },
    )
    assert [a["id"] for a in response.data["results"]] == [on_start.pk]


def test_a_filter_timestamp_without_an_offset_is_rejected(alice, auth_client):
    response = auth_client(alice).get(APPOINTMENTS, {"starts_after": "2030-01-07T00:00:00"})
    assert response.status_code == 400


def test_the_date_filter_still_respects_role_scoping(provider, alice, make_user, auth_client):
    make_appointment(provider, alice, NOON)
    bob = make_user(email="bob@example.com")
    response = auth_client(bob).get(APPOINTMENTS, {"starts_after": "2030-01-01T00:00:00Z"})
    assert response.data["results"] == []


def test_appointments_expose_the_providers_timezone(provider, alice, auth_client):
    make_appointment(provider, alice, NOON)
    result = auth_client(alice).get(APPOINTMENTS).data["results"][0]
    assert result["provider_timezone"] == "Asia/Kolkata"
