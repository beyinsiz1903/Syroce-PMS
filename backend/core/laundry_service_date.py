"""Service day is separate from the open accounting/posting day."""
import re
from datetime import date

from fastapi import HTTPException


def laundry_service_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HTTPException(422, "Hizmet günü YYYY-MM-DD biçiminde olmalıdır")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(422, "Hizmet günü geçersiz") from exc


def validate_laundry_stay_day(value, booking):
    day = laundry_service_date(value)
    try:
        arrival = date.fromisoformat(str(booking.get("check_in") or "")[:10])
        departure = date.fromisoformat(str(booking.get("check_out") or "")[:10])
    except ValueError as exc:
        raise HTTPException(409, "Hizmet günü için konaklama tarihleri doğrulanamadı") from exc
    if not arrival <= date.fromisoformat(day) <= departure:
        raise HTTPException(409, "Hizmet günü giriş ve çıkış günleri arasında olmalıdır")
    return day
