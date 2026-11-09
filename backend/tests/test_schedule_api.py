from datetime import timedelta

import pytest

from apps.accounts.models import Role
from apps.scheduling.models import AvailabilityRule, TimeOff
from tests.helpers import future_slot, open_all_week

pytestmark = pytest.mark.django_db

PROVIDERS = "/api/providers/"
RULES = "/api/me/availability-rules/"
TIME_OFF = "/api/me/time-off/"


# ---- availability rules (a provider's own) ---------------------------------------------


def rule_payload(**overrides):
    data = {"weekday": 0, "start_time": "09:00", "end_time": "12:00"}
    data.update(overrides)
    return data


def test_provider_can_create_a_rule(make_provider, auth_client):
    provider = make_provider()
    client = auth_client(provider.user)
    response = client.post(RULES, rule_payload(), format="json")
    assert response.status_code == 201
    assert provider.rules.count() == 1


def test_rule_with_end_before_start_is_rejected(make_provider, auth_client):
    client = auth_client(make_provider().user)
    response = client.post(RULES, rule_payload(start_time="12:00", end_time="09:00"), format="json")
    assert response.status_code == 400


def test_overlapping_rule_on_the_same_weekday_is_rejected(make_provider, auth_client):
    client = auth_client(make_provider().user)
    assert client.post(RULES, rule_payload(), format="json").status_code == 201
    clash = client.post(RULES, rule_payload(start_time="11:00", end_time="14:00"), format="json")
    assert clash.status_code == 400
    touching = client.post(RULES, rule_payload(start_time="12:00", end_time="14:00"), format="json")
    assert touching.status_code == 201  # back-to-back is fine


def test_same_hours_on_another_weekday_is_fine(make_provider, auth_client):
    client = auth_client(make_provider().user)
    client.post(RULES, rule_payload(), format="json")
    assert client.post(RULES, rule_payload(weekday=1), format="json").status_code == 201


def test_overlap_is_ignored_when_validity_dates_do_not_intersect(make_provider, auth_client):
    client = auth_client(make_provider().user)
    january = rule_payload(valid_from="2030-01-01", valid_to="2030-01-31")
    february = rule_payload(valid_from="2030-02-01", valid_to="2030-02-28")
    assert client.post(RULES, january, format="json").status_code == 201
    assert client.post(RULES, february, format="json").status_code == 201


def test_patch_can_change_a_rule_but_not_into_an_overlap(make_provider, auth_client):
    client = auth_client(make_provider().user)
    first = client.post(RULES, rule_payload(), format="json").data
    second = client.post(
        RULES, rule_payload(start_time="14:00", end_time="16:00"), format="json"
    ).data

    ok = client.patch(f"{RULES}{first['id']}/", {"end_time": "11:00"}, format="json")
    assert ok.status_code == 200 and ok.data["end_time"] == "11:00:00"

    clash = client.patch(f"{RULES}{second['id']}/", {"start_time": "10:00"}, format="json")
    assert clash.status_code == 400


def test_rule_can_be_deleted(make_provider, auth_client):
    provider = make_provider()
    client = auth_client(provider.user)
    rule_id = client.post(RULES, rule_payload(), format="json").data["id"]
    assert client.delete(f"{RULES}{rule_id}/").status_code == 204
    assert provider.rules.count() == 0


def test_provider_cannot_touch_another_providers_rule(make_provider, auth_client):
    mine, theirs = make_provider(), make_provider()
    rule = AvailabilityRule.objects.create(
        provider=theirs, weekday=0, start_time="09:00", end_time="12:00"
    )
    client = auth_client(mine.user)
    assert client.get(RULES).data["results"] == []
    assert (
        client.patch(f"{RULES}{rule.id}/", {"end_time": "11:00"}, format="json").status_code == 404
    )
    assert client.delete(f"{RULES}{rule.id}/").status_code == 404
    assert AvailabilityRule.objects.filter(pk=rule.pk).exists()


@pytest.mark.parametrize("path", [RULES, TIME_OFF])
def test_schedule_endpoints_are_for_providers_only(make_user, auth_client, api_client, path):
    assert api_client.get(path).status_code == 401
    for role in (Role.CLIENT, Role.ADMIN):
        user = make_user(email=f"{role}@example.com", role=role)
        assert auth_client(user).get(path).status_code == 403


@pytest.mark.parametrize("path", [RULES, TIME_OFF])
def test_provider_account_without_a_profile_gets_a_clear_404(make_user, auth_client, path):
    user = make_user(email="orphan@example.com", role=Role.PROVIDER)
    assert auth_client(user).get(path).status_code == 404


# ---- time off --------------------------------------------------------------------------


def test_time_off_create_list_delete_and_effect_on_slots(make_provider, make_user, auth_client):
    provider = open_all_week(make_provider())
    start = future_slot(provider)  # 09:00 local
    client = auth_client(provider.user)

    created = client.post(
        TIME_OFF,
        {
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=1)).isoformat(),
            "reason": "Conference",
        },
        format="json",
    )
    assert created.status_code == 201
    assert len(client.get(TIME_OFF).data["results"]) == 1

    day = start.date().isoformat()
    viewer = auth_client(make_user())
    slots = viewer.get(f"{PROVIDERS}{provider.id}/slots/", {"date": day}).data
    assert len(slots) == 4  # two of the six slots are gone

    assert client.delete(f"{TIME_OFF}{created.data['id']}/").status_code == 204
    assert len(viewer.get(f"{PROVIDERS}{provider.id}/slots/", {"date": day}).data) == 6


def test_time_off_must_end_after_it_starts(make_provider, auth_client):
    provider = make_provider()
    start = future_slot(provider)
    response = auth_client(provider.user).post(
        TIME_OFF,
        {"starts_at": start.isoformat(), "ends_at": (start - timedelta(hours=1)).isoformat()},
        format="json",
    )
    assert response.status_code == 400


def test_provider_cannot_delete_another_providers_time_off(make_provider, auth_client):
    mine, theirs = make_provider(), make_provider()
    start = future_slot(theirs)
    entry = TimeOff.objects.create(
        provider=theirs, starts_at=start, ends_at=start + timedelta(hours=1)
    )
    assert auth_client(mine.user).delete(f"{TIME_OFF}{entry.id}/").status_code == 404
    assert TimeOff.objects.filter(pk=entry.pk).exists()
