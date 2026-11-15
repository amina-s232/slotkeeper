"""Create believable demo data so the API (and later the frontend) has something to show.

Safe to run repeatedly: users and rules are created once, bookings only if none exist yet.
Refuses to run when DEBUG is off, because it creates accounts with a publicly known password.
"""

from datetime import time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.scheduling.models import Appointment, AvailabilityRule, Provider
from apps.scheduling.services.booking import book_appointment
from apps.scheduling.services.slots import free_slots

PASSWORD = "demo-pass-123"

PROVIDERS = [
    ("dr.rao@demo.test", "Dr Rao", "General practice", "Asia/Kolkata"),
    ("dr.hughes@demo.test", "Dr Hughes", "Dentistry", "Europe/London"),
]
CLIENTS = [
    ("asha@demo.test", "Asha Nair"),
    ("ravi@demo.test", "Ravi Menon"),
    ("meera@demo.test", "Meera Iyer"),
]


def _user(email, name, role):
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(email=email, password=PASSWORD, full_name=name, role=role)
    return user


class Command(BaseCommand):
    help = "Create demo users, working hours and a few appointments (development only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the demo clients' appointments first, then book fresh ones.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo creates accounts with a known password; DEBUG must be on."
            )
        if options["reset"]:
            Appointment.objects.filter(client__email__endswith="@demo.test").delete()

        if not User.objects.filter(email="admin@demo.test").exists():
            User.objects.create_superuser(
                email="admin@demo.test", password=PASSWORD, full_name="Demo Admin"
            )

        providers = []
        for email, name, specialty, tz in PROVIDERS:
            user = _user(email, name, Role.PROVIDER)
            provider, created = Provider.objects.get_or_create(
                user=user, defaults={"display_name": name, "specialty": specialty, "timezone": tz}
            )
            if created:
                for weekday in range(5):  # Monday to Friday, with a lunch break
                    for start, end in ((time(9), time(12)), (time(14), time(17))):
                        AvailabilityRule.objects.create(
                            provider=provider, weekday=weekday, start_time=start, end_time=end
                        )
            providers.append(provider)

        clients = [_user(email, name, Role.CLIENT) for email, name in CLIENTS]

        booked = 0
        if not Appointment.objects.filter(client__in=clients).exists():
            today = timezone.now().date()
            for provider, client in zip(providers * 2, clients, strict=False):
                for offset in range(1, 15):
                    slots = free_slots(provider, today + timedelta(days=offset))
                    if slots:
                        book_appointment(client=client, provider=provider, starts_at=slots[0].start)
                        booked += 1
                        break

        self.stdout.write(self.style.SUCCESS(f"Demo data ready ({booked} new appointments)."))
        self.stdout.write(f"Log in with any *@demo.test email and password: {PASSWORD}")
