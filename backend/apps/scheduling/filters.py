import django_filters
from django import forms
from django.utils.dateparse import parse_datetime

from .models import Appointment


class AwareIsoDateTimeField(django_filters.fields.IsoDateTimeField):
    """Accept ISO 8601 only WITH a UTC offset, so a filter never silently assumes a timezone."""

    def to_python(self, value):
        if value not in self.empty_values:
            parsed = parse_datetime(str(value).strip())
            if parsed is not None and parsed.tzinfo is None:
                raise forms.ValidationError(
                    "Include a timezone offset, e.g. 2030-01-07T00:00:00Z or ...+05:30."
                )
        return super().to_python(value)


class AwareIsoDateTimeFilter(django_filters.IsoDateTimeFilter):
    field_class = AwareIsoDateTimeField


class AppointmentFilter(django_filters.FilterSet):
    starts_after = AwareIsoDateTimeFilter(
        field_name="starts_at", lookup_expr="gte", help_text="Start at or after this instant."
    )
    starts_before = AwareIsoDateTimeFilter(
        field_name="starts_at", lookup_expr="lt", help_text="Start strictly before this instant."
    )

    class Meta:
        model = Appointment
        fields = ["status", "provider", "starts_after", "starts_before"]
