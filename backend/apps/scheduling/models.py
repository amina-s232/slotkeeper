from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import (
    DateTimeRangeField,
    RangeBoundary,
    RangeOperators,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Func, Q


def validate_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValidationError(f"'{value}' is not a valid IANA timezone.") from None


class Provider(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="provider_profile"
    )
    display_name = models.CharField(max_length=150)
    specialty = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)
    timezone = models.CharField(
        max_length=64, default="Asia/Kolkata", validators=[validate_timezone]
    )
    slot_minutes = models.PositiveSmallIntegerField(default=30)
    booking_window_days = models.PositiveSmallIntegerField(default=30)
    min_notice_hours = models.PositiveSmallIntegerField(default=2)
    cancel_cutoff_hours = models.PositiveSmallIntegerField(default=4)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(slot_minutes__gt=0), name="provider_slot_minutes_positive"
            ),
        ]

    def __str__(self):
        return self.display_name

class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"

class AvailabilityRule(models.Model):
    """Weekly recurring working hours, interpreted in the provider's timezone."""

    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="rules")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["provider", "weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")), name="rule_end_after_start"
            ),
        ]

    def __str__(self):
        return f"{self.provider} {self.get_weekday_display()} {self.start_time}-{self.end_time}"

class TimeOff(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="time_off")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["starts_at"]
        verbose_name_plural = "time off"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="timeoff_ends_after_start"
            ),
        ]

    def __str__(self):
        return f"{self.provider} off {self.starts_at:%Y-%m-%d %H:%M}"


class TsTzRange(Func):
    """SQL TSTZRANGE(start, end, bounds) so the database can compare time ranges."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class AppointmentStatus(models.TextChoices):
    BOOKED = "booked", "Booked"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"
    NO_SHOW = "no_show", "No show"

class Appointment(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name="appointments")
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(
        max_length=10, choices=AppointmentStatus.choices, default=AppointmentStatus.BOOKED
    )
    notes = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["provider", "starts_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="appointment_ends_after_start"
            ),
            # The guarantee: no two *booked* appointments for one provider may overlap.
            ExclusionConstraint(
                name="no_overlapping_booked_appointments",
                expressions=[
                    (TsTzRange("starts_at", "ends_at", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("provider", RangeOperators.EQUAL),
                ],
                condition=Q(status="booked"),
            ),
                ExclusionConstraint(
                name="client_cannot_double_book",
                expressions=[
                    (TsTzRange("starts_at", "ends_at", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("client", RangeOperators.EQUAL),
                ],
                condition=Q(status="booked"),
            ),

        ]

    def __str__(self):
        return f"{self.provider} @ {self.starts_at:%Y-%m-%d %H:%M}"
