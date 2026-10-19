"""Report periods in the hotel's own calendar.

A report day is the hotel's local calendar day (``tenant_settings.timezone``,
Europe/Istanbul when unset, as the business-date service). A period
``start..end`` covers whole local days: from ``start`` 00:00 local up to, not
including, the day after ``end`` 00:00 local — so the end day is included to
its last second and nothing of the next day is.

Stored instants are ISO strings in most collections and BSON datetimes in a
few; ``instant_between`` matches both. Malformed ``YYYY-MM`` / ``YYYY-MM-DD``
input is a 422, not a server error.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

DEFAULT_ZONE = "Europe/Istanbul"


async def hotel_zone(database, tenant_id: str) -> ZoneInfo:
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "timezone": 1}) or {}
    try:
        return ZoneInfo(str(settings.get("timezone") or DEFAULT_ZONE))
    except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
        return ZoneInfo(DEFAULT_ZONE)


def local_today(zone: ZoneInfo, now: datetime) -> date:
    reference = now if now.tzinfo else now.replace(tzinfo=UTC)
    return reference.astimezone(zone).date()


def day_bounds(start: date, end: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """[start 00:00 local, day after end 00:00 local) as UTC instants."""
    if end < start:
        raise HTTPException(422, "Bitiş tarihi başlangıçtan önce olamaz")
    lower = datetime.combine(start, time.min, tzinfo=zone).astimezone(UTC)
    upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return lower, upper


# Every UTC offset in use lies within -12:00..+14:00, so a stored local text
# for an instant in [lower, upper) sorts inside this widened text window.
_TEXT_SLACK_BEFORE = _TEXT_SLACK_AFTER = timedelta(hours=14)


def instant_between(field: str, lower: datetime, upper: datetime) -> dict:
    """``field`` in [lower, upper) as an instant: BSON dates, UTC text and text
    with any offset ("2026-10-19T22:00:00+03:00"). Text is not compared as
    text alone — "…22:00+03:00" sorts after "…21:00+00:00" yet is earlier."""
    text_window = {"$gte": (lower - _TEXT_SLACK_BEFORE).strftime("%Y-%m-%dT%H:%M:%S"),
                   "$lt": (upper + _TEXT_SLACK_AFTER).strftime("%Y-%m-%dT%H:%M:%S")}
    instant = {"$convert": {"input": f"${field}", "to": "date", "onError": None, "onNull": None}}
    return {"$and": [
        {"$or": [{field: {"$gte": lower, "$lt": upper}}, {field: text_window}]},
        {"$expr": {"$and": [{"$gte": [instant, lower]}, {"$lt": [instant, upper]}]}},
    ]}


def parse_day(value: str, name: str = "date") -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        raise HTTPException(422, f"{name} YYYY-AA-GG biçiminde olmalıdır") from None


def parse_month(value: str) -> tuple[date, date]:
    """'YYYY-MM' -> (first day, last day)."""
    try:
        year, month = (int(part) for part in str(value).split("-"))
        first = date(year, month, 1)
    except (TypeError, ValueError):
        raise HTTPException(422, "Ay YYYY-AA biçiminde olmalıdır") from None
    last = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
    return first, last


def instant_value(value) -> datetime | None:
    """A stored instant (ISO text or datetime) as an aware UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
