"""A provider reading and changing their own profile and booking rules."""

import pytest

from tests.helpers import open_all_week

pytestmark = pytest.mark.django_db

MY_PROVIDER = "/api/me/provider/"


@pytest.fixture
def provider(make_provider):
    return open_all_week(make_provider())


@pytest.fixture
def alice(make_user):
    return make_user(email="alice@example.com")


# ---- a provider's own settings ---------------------------------------------------------


def test_provider_reads_their_own_settings(provider, auth_client):
    response = auth_client(provider.user).get(MY_PROVIDER)
    assert response.status_code == 200
    assert response.data["cancel_cutoff_hours"] == 4
    assert response.data["is_active"] is True


def test_provider_changes_their_settings(provider, auth_client):
    response = auth_client(provider.user).patch(
        MY_PROVIDER,
        {"cancel_cutoff_hours": 12, "slot_minutes": 20, "specialty": "ENT"},
        format="json",
    )
    assert response.status_code == 200
    provider.refresh_from_db()
    assert (provider.cancel_cutoff_hours, provider.slot_minutes, provider.specialty) == (
        12,
        20,
        "ENT",
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"timezone": "Mars/Olympus"},
        {"slot_minutes": 0},
        {"slot_minutes": 1000},
        {"booking_window_days": 0},
        {"cancel_cutoff_hours": -1},
    ],
)
def test_invalid_settings_are_rejected_and_nothing_changes(provider, auth_client, bad):
    before = provider.slot_minutes
    response = auth_client(provider.user).patch(MY_PROVIDER, bad, format="json")
    assert response.status_code == 400
    provider.refresh_from_db()
    assert provider.slot_minutes == before


def test_a_client_cannot_use_the_provider_settings_endpoint(alice, auth_client):
    assert auth_client(alice).get(MY_PROVIDER).status_code == 403


def test_a_provider_cannot_change_which_account_owns_the_profile(provider, make_user, auth_client):
    other = make_user(email="other@example.com")
    auth_client(provider.user).patch(MY_PROVIDER, {"user": other.pk}, format="json")
    provider.refresh_from_db()
    assert provider.user != other


def test_settings_endpoint_requires_login(api_client):
    assert api_client.get(MY_PROVIDER).status_code == 401
