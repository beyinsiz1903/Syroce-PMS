"""One read-only accounting-day scope for POS summary and history."""
from datetime import date, timedelta

from fastapi import HTTPException


def pos_report_period(start=None, end=None):
    bounds = {}
    try:
        if start:
            bounds["$gte"] = date.fromisoformat(start).isoformat()
        if end:
            bounds["$lt"] = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
        if start and end and start > end:
            raise ValueError
    except (ValueError, OverflowError):
        raise HTTPException(422, "POS tarih aralığı geçersiz") from None
    if not bounds:
        return {}
    return {"$or": [
        {"business_date": bounds},
        {"business_date": {"$exists": False}, "created_at": bounds},
    ]}
