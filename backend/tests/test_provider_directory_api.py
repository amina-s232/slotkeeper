import pytest

from tests.helpers import future_slot, open_all_week

pytestmark = pytest.mark.django_db

PROVIDERS = "/api/providers/"


# ---- directory and slots (any logged-in user) ------------------------------------------


def test_directory_requires_login(api_client):
    assert api_client.get(PROVIDERS).status_code == 401


def test_directory_lists_only_active_providers_and_filters_by_specialty(
    make_provider, make_user, auth_client
):
    make_provider(display_name="Dr Teeth", specialty="Dentist")
    make_provider(display_name="Dr Heart", specialty="Cardiologist")
    make_provider(display_name="Dr Gone", specialty="Dentist", is_active=False)
    client = auth_client(make_user())

    names = {p["display_name"] for p in client.get(PROVIDERS).data["results"]}
    assert names == {"Dr Teeth", "Dr Heart"}

    dentists = client.get(PROVIDERS, {"specialty": "Dentist"}).data["results"]
    assert [p["display_name"] for p in dentists] == ["Dr Teeth"]


def test_directory_does_not_leak_account_details(make_provider, make_user, auth_client):
    provider = make_provider()
    data = auth_client(make_user()).get(f"{PROVIDERS}{provider.id}/").data
    assert "user" not in data and "email" not in data


def test_inactive_provider_is_a_404(make_provider, make_user, auth_client):
    provider = make_provider(is_active=False)
    assert auth_client(make_user()).get(f"{PROVIDERS}{provider.id}/").status_code == 404


def test_slots_endpoint_returns_free_slots(make_provider, make_user, auth_client):
    provider = open_all_week(make_provider())
    day = future_slot(provider).date()
    client = auth_client(make_user())

    response = client.get(f"{PROVIDERS}{provider.id}/slots/", {"date": day.isoformat()})
    assert response.status_code == 200
    assert len(response.data) == 6  # 09:00-12:00 in 30-minute slots
    assert {"starts_at", "ends_at"} == set(response.data[0])


def test_slots_endpoint_needs_a_valid_date(make_provider, make_user, auth_client):
    provider = make_provider()
    client = auth_client(make_user())
    assert client.get(f"{PROVIDERS}{provider.id}/slots/").status_code == 400
    assert client.get(f"{PROVIDERS}{provider.id}/slots/", {"date": "tomorrow"}).status_code == 400
