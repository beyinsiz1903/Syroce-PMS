"""Authoritative immutability guard for historical reservation data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import HTTPException, status

from core.business_date_service import ensure_business_date_initialized

_TERMINAL_STATUSES = {"checked_out", "cancelled", "no_show"}
_IN_HOUSE_STATUSES = {"checked_in", "in_house"}


def _date_only(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value.strip()) >= 10:
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def reservation_is_historical(booking: dict, business_date: str) -> bool:
    """Return whether operational reservation facts must be read-only.

    A completed/cancelled/no-show stay is immutable immediately. An older
    non-terminal legacy row is also immutable once its departure date is
    before the hotel's authoritative PMS business date.
    """
    booking_status = str(booking.get("status") or "").strip().lower()
    if booking_status in _TERMINAL_STATUSES:
        return True
    # An overdue guest still physically in-house must remain operable so the
    # front desk can extend or complete the stay. It becomes immutable at
    # checkout; stale pre-arrival rows are locked once their stay is past.
    if booking_status in _IN_HOUSE_STATUSES:
        return False
    departure = _date_only(booking.get("check_out"))
    active_day = _date_only(business_date)
    return bool(departure and active_day and departure < active_day)


async def ensure_reservation_mutable(db, tenant_id: str, booking: dict) -> None:
    business_date = await ensure_business_date_initialized(db, tenant_id)
    active_day = business_date["business_date"]
    if reservation_is_historical(booking, active_day):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Geçmiş veya tamamlanmış rezervasyonlar salt okunurdur; fiyat ve konaklama bilgileri değiştirilemez."),
        )
