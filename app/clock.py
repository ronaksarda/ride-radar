"""City-local time. Servers usually run in UTC, so never use naive datetime.now() for the hour of day."""
from datetime import datetime, timedelta, timezone

from app import config

CITY_TZ = timezone(timedelta(minutes=config.TZ_OFFSET_MINUTES))


def now():
    """Current time in the city, timezone-aware."""
    return datetime.now(CITY_TZ)


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds")
