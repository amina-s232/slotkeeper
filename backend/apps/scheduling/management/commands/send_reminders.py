from django.core.management.base import BaseCommand

from apps.scheduling.services.reminders import send_due_reminders


class Command(BaseCommand):
    help = "Email a reminder for every booked appointment starting soon. Safe to run in parallel."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Remind for appointments starting within this many hours.",
        )

    def handle(self, *args, **options):
        sent = send_due_reminders(hours=options["hours"])
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder(s)."))
