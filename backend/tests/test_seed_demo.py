import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.scheduling.models import Appointment, AvailabilityRule, Provider

pytestmark = pytest.mark.django_db


def test_seed_demo_refuses_to_run_when_debug_is_off(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo")
    assert User.objects.count() == 0


def test_seed_demo_creates_data_and_is_safe_to_repeat(settings):
    settings.DEBUG = True
    call_command("seed_demo")
    counts = (
        User.objects.count(),
        Provider.objects.count(),
        AvailabilityRule.objects.count(),
        Appointment.objects.count(),
    )
    assert counts[0] == 6  # admin + 2 providers + 3 clients
    assert counts[1] == 2
    assert counts[2] == 20  # 2 providers x 5 weekdays x 2 sessions
    assert counts[3] == 3
    call_command("seed_demo")
    assert (
        User.objects.count(),
        Provider.objects.count(),
        AvailabilityRule.objects.count(),
        Appointment.objects.count(),
    ) == counts


def test_seeded_accounts_can_log_in(settings, api_client):
    settings.DEBUG = True
    call_command("seed_demo")
    response = api_client.post(
        "/api/auth/token/",
        {"email": "asha@demo.test", "password": "demo-pass-123"},
        format="json",
    )
    assert response.status_code == 200


def test_reset_gives_a_fresh_set_of_appointments(settings):
    settings.DEBUG = True
    call_command("seed_demo")
    Appointment.objects.all().update(status="cancelled")
    call_command("seed_demo")  # without --reset, nothing is re-booked
    assert Appointment.objects.filter(status="booked").count() == 0
    call_command("seed_demo", "--reset")
    assert Appointment.objects.count() == 3
    assert Appointment.objects.filter(status="booked").count() == 3
