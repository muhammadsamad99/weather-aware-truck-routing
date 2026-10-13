from datetime import UTC, datetime, timedelta

from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from .checkpoints import INTERVALS_MI

MAX_LOAD_LB = 80_000
MAX_DAYS_AHEAD = 14
PAST_GRACE = timedelta(hours=1)


class PlaceField(serializers.Field):
    """A place as text to look up ("Chicago, IL"), or as {"label", "lat", "lon"} from a suggestion."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            text = " ".join(data.split())
            if not text or len(text) > 200:
                raise serializers.ValidationError("Enter a place (up to 200 characters).")
            return text
        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("A place needs numeric lat and lon.") from None
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise serializers.ValidationError("Latitude or longitude is out of range.")
            label = str(data.get("label") or f"{lat:.4f}, {lon:.4f}")[:200]
            return {"label": label, "lat": lat, "lon": lon}
        raise serializers.ValidationError("Enter a place.")

    def to_representation(self, value):
        return value


class AwareDateTimeField(serializers.DateTimeField):
    """A date-time that must carry its time zone. DRF would read a naive one as UTC, which silently shifts
    a departure written in local time."""

    def to_internal_value(self, value):
        parsed = parse_datetime(value) if isinstance(value, str) else None
        if parsed is not None and parsed.tzinfo is None:
            raise serializers.ValidationError("Give the departure with a time zone, for example 2026-10-15T08:00:00Z.")
        return super().to_internal_value(value)


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure = AwareDateTimeField()
    load_lb = serializers.FloatField(min_value=1, max_value=MAX_LOAD_LB)
    interval_mi = serializers.ChoiceField(choices=INTERVALS_MI)

    def validate_departure(self, value: datetime) -> datetime:
        now = datetime.now(UTC)
        if value < now - PAST_GRACE:
            raise serializers.ValidationError("The departure is in the past.")
        if value > now + timedelta(days=MAX_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Forecasts reach {MAX_DAYS_AHEAD} days ahead; choose an earlier departure.")
        return value
