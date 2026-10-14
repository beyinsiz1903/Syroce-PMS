"""Hotel-night overlap filter for booking availability queries.

Bookings store ``check_in``/``check_out`` as ISO strings, either date-only
(``2026-10-15``) or with the operational hour (``2026-10-15T14:00:00+00:00``,
``2026-10-15T12:00:00+00:00``). Comparing those strings directly against
``<date>T00:00:00`` treats a guest departing at 12:00 as still occupying the
departure night, so a room that turns over on the arrival day looked sold.

A booking occupies the nights ``[check_in, check_out)``; this filter compares
only the calendar-date prefix of both stored values.
"""

from __future__ import annotations

from datetime import date, timedelta


def _next_day(day: str) -> str:
    return (date.fromisoformat(day[:10]) + timedelta(days=1)).isoformat()


def _date_prefix(field: str) -> dict:
    return {"$substrBytes": [{"$toString": f"${field}"}, 0, 10]}


def stay_overlap_filter(check_in: str, check_out: str) -> dict:
    """Return a Mongo filter matching bookings that occupy a night in ``[check_in, check_out)``.

    The plain range conditions keep the query index-friendly and are a superset
    of the overlap; ``$expr`` then compares the exact calendar dates.
    """
    start = check_in[:10]
    end = check_out[:10]
    return {
        "check_in": {"$lt": _next_day(end)},
        "check_out": {"$gt": start},
        "$expr": {
            "$and": [
                {"$lt": [_date_prefix("check_in"), end]},
                {"$gt": [_date_prefix("check_out"), start]},
            ]
        },
    }
