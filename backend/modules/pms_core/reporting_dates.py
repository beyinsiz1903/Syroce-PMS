"""Inclusive report dates, half-open Mongo ranges for ISO and BSON dates."""

from datetime import UTC, date, datetime, time, timedelta


def date_period_match(field: str, first: date, last: date) -> dict:
    next_day = last + timedelta(days=1)
    return {
        "$or": [
            {field: {"$gte": first.isoformat(), "$lt": next_day.isoformat()}},
            {field: {"$gte": datetime.combine(first, time.min, UTC), "$lt": datetime.combine(next_day, time.min, UTC)}},
        ]
    }
