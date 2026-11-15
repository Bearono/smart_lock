"""Serialize existing server wall-clock timestamps without guessing their timezone."""
from datetime import timezone
from zoneinfo import ZoneInfo
from flask import current_app


def timestamp(value):
    if value is None:
        return None
    zone = current_app.config.get('SERVER_TIMEZONE')
    if value.tzinfo is None and zone:
        value = value.replace(tzinfo=timezone.utc if zone == 'UTC' else ZoneInfo(zone))
    return value.isoformat(timespec='seconds')
