from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
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
