from rest_framework import serializers

from .models import Provider


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
