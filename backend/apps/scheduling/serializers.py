from rest_framework import serializers

from .models import AvailabilityRule, Provider, TimeOff


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = [
            "id",
            "display_name",
            "specialty",
            "bio",
            "timezone",
            "slot_minutes",
            "booking_window_days",
            "min_notice_hours",
            "cancel_cutoff_hours",
        ]
        read_only_fields = fields


class SlotQuerySerializer(serializers.Serializer):
    date = serializers.DateField(help_text="Day to check, in the provider's timezone (YYYY-MM-DD).")


class SlotSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()

def _ranges_intersect(a_from, a_to, b_from, b_to) -> bool:
    """Do two optional date ranges overlap? None means unbounded on that side."""
    return (a_from is None or b_to is None or a_from <= b_to) and (
        b_from is None or a_to is None or b_from <= a_to
    )


class AvailabilityRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityRule
        fields = ["id", "weekday", "start_time", "end_time", "valid_from", "valid_to"]

    def _value(self, attrs, name):
        """New value if the request supplies one, otherwise the stored one (for PATCH)."""
        if name in attrs:
            return attrs[name]
        return getattr(self.instance, name) if self.instance else None

    def validate(self, attrs):
        weekday = self._value(attrs, "weekday")
        start, end = self._value(attrs, "start_time"), self._value(attrs, "end_time")
        valid_from, valid_to = self._value(attrs, "valid_from"), self._value(attrs, "valid_to")

        if start >= end:
            raise serializers.ValidationError({"end_time": "Must be after start_time."})
        if valid_from and valid_to and valid_from > valid_to:
            raise serializers.ValidationError({"valid_to": "Must not be before valid_from."})

        clashes = self.context["provider"].rules.filter(
            weekday=weekday, start_time__lt=end, end_time__gt=start
        )
        if self.instance:
            clashes = clashes.exclude(pk=self.instance.pk)
        if any(_ranges_intersect(valid_from, valid_to, c.valid_from, c.valid_to) for c in clashes):
            raise serializers.ValidationError("This overlaps another rule on the same weekday.")
        return attrs


class TimeOffSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOff
        fields = ["id", "starts_at", "ends_at", "reason"]

    def validate(self, attrs):
        if attrs["ends_at"] <= attrs["starts_at"]:
            raise serializers.ValidationError({"ends_at": "Must be after starts_at."})
        return attrs
