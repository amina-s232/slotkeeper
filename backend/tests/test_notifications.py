from datetime import UTC, datetime, time, timedelta

import pytest
from django.core import mail

from apps.accounts.models import Role
from apps.scheduling import services
from apps.scheduling.models import Appointment, AppointmentStatus, AvailabilityRule
from apps.scheduling.services.booking import book_appointment
from apps.scheduling.services.lifecycle import DeadlinePassed, cancel_appointment

pytestmark = pytest.mark.django_db

NOW = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)
NINE_IST = datetime(2030, 1, 7, 3, 30, tzinfo=UTC)


@pytest.fixture
def provider(make_provider):
    provider = make_provider()
    AvailabilityRule.objects.create(
        provider=provider, weekday=0, start_time=time(9), end_time=time(12)
    )
    return provider


@pytest.fixture
def alice(make_user):
    return make_user(email="alice@example.com")


@pytest.fixture
def booked(provider, alice):
    return book_appointment(client=alice, provider=provider, starts_at=NINE_IST, now=NOW)


def test_client_cancelling_notifies_the_provider(
    provider, alice, booked, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        cancel_appointment(appointment_id=booked.pk, actor=alice, now=NOW)
    assert [m.to for m in mail.outbox] == [[provider.user.email]]
    assert "09:00" in mail.outbox[0].body


def test_provider_cancelling_notifies_the_client(
    provider, alice, booked, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        cancel_appointment(appointment_id=booked.pk, actor=provider.user, now=NOW)
    assert [m.to for m in mail.outbox] == [[alice.email]]
    assert provider.display_name in mail.outbox[0].body


def test_admin_cancelling_notifies_the_client(
    alice, booked, make_user, django_capture_on_commit_callbacks
):
    admin = make_user(email="admin@example.com", role=Role.ADMIN)
    with django_capture_on_commit_callbacks(execute=True):
        cancel_appointment(appointment_id=booked.pk, actor=admin, now=NOW)
    assert [m.to for m in mail.outbox] == [[alice.email]]


def test_a_refused_cancellation_sends_nothing(alice, booked, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(DeadlinePassed):
            cancel_appointment(
                appointment_id=booked.pk, actor=alice, now=NINE_IST - timedelta(hours=1)
            )
    assert mail.outbox == []


def test_a_broken_mail_server_does_not_undo_the_cancellation(
    alice, booked, monkeypatch, django_capture_on_commit_callbacks
):
    def broken(**kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(services.notifications, "send_mail", broken)
    with django_capture_on_commit_callbacks(execute=True):
        cancel_appointment(appointment_id=booked.pk, actor=alice, now=NOW)
    assert Appointment.objects.get(pk=booked.pk).status == AppointmentStatus.CANCELLED
