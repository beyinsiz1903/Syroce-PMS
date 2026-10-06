"""Auto-split from reports.py — backward-compatible sub-router."""

import asyncio
import logging
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

from core.business_date_service import (
    accounting_day_match,
    accounting_period_match,
    ensure_business_date_initialized,
)
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.reporting_financials import REPORTING_CURRENCY, reporting_collection_amount
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import calculate_stay_night_metrics, load_stay_night_metrics

security = HTTPBearer()

try:
    from domains.pms.night_audit_module import AuditStatus, AutomaticPosting, NightAuditRecord
except ImportError:
    NightAuditRecord = None
    AuditStatus = None
    AutomaticPosting = None


try:
    from infra.logging_service import get_logging_service
except ImportError:
    get_logging_service = None

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)
sub_router = APIRouter()


NON_CASH_PAYMENT_METHODS = {"discount", "city_ledger", "complimentary", "correction", "ar"}
IN_HOUSE_STATUSES = {"checked_in", "in_house", "checked_out"}
ARRIVAL_STATUSES = {"confirmed", "guaranteed", "checked_in", "checked_out"}
ROOM_CHARGE_CATEGORIES = {"room", "accommodation", "room_charge"}
FNB_CHARGE_CATEGORIES = {
    "alcohol",
    "alcoholic_beverage",
    "appetizer",
    "bar",
    "beverage",
    "cafe",
    "dessert",
    "drink",
    "fb",
    "f&b",
    "fnb",
    "food",
    "food_and_beverage",
    "food_beverage",
    "mini_bar",
    "minibar",
    "restaurant",
    "room_service",
}

_FX_RECEIPT_RE = re.compile(
    r"\[Döviz Çevirici\]\s*[\d.,]+\s+[A-Z]{3}\s*=\s*([\d.,]+)\s+([A-Z]{3})",
    re.IGNORECASE,
)


def _received_payment_amount(payment: dict, fallback_currency: str = "TRY") -> dict:
    """Return the currency physically received, not the booking ledger currency."""
    def _signed(amount: float) -> float:
        return -amount if str(payment.get("payment_type") or "").lower() == "refund" and amount > 0 else amount

    structured_amount = payment.get("received_amount")
    structured_currency = payment.get("received_currency")
    if structured_amount is not None and structured_currency:
        try:
            amount = float(structured_amount)
            if amount > 0:
                return {"amount": _signed(amount), "currency": str(structured_currency).upper()}
        except (TypeError, ValueError):
            pass
    match = _FX_RECEIPT_RE.search(str(payment.get("notes") or ""))
    if match:
        try:
            return {"amount": _signed(float(match.group(1).replace(",", "."))), "currency": match.group(2).upper()}
        except ValueError:
            pass
    return {
        "amount": _signed(float(payment.get("amount") or 0)),
        "currency": str(payment.get("currency") or fallback_currency or "TRY").upper(),
    }


def _currency_code(value, fallback: str = "TRY") -> str:
    code = str(value or fallback or "TRY").strip().upper()
    return code if len(code) == 3 and code.isalpha() else str(fallback or "TRY").upper()


def _add_currency_amount(target: dict[str, float], currency, amount) -> None:
    code = _currency_code(currency)
    target[code] = target.get(code, 0.0) + float(amount or 0)


def _currency_breakdown(rows: list[dict], amount_getter, currency_getter) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        _add_currency_amount(totals, currency_getter(row), amount_getter(row))
    return {code: round(amount, 2) for code, amount in sorted(totals.items()) if round(amount, 2) != 0}


def _merge_currency_breakdowns(*breakdowns: dict[str, float]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for breakdown in breakdowns:
        for currency, amount in (breakdown or {}).items():
            _add_currency_amount(totals, currency, amount)
    return {code: round(amount, 2) for code, amount in sorted(totals.items()) if round(amount, 2) != 0}


def _single_currency_amount(breakdown: dict[str, float]) -> float:
    """Legacy scalar compatibility without ever adding unlike currencies."""
    values = [float(amount) for amount in (breakdown or {}).values() if float(amount) != 0]
    return round(values[0], 2) if len(values) == 1 else 0.0


def _normalized_room_status(value) -> str:
    """Map legacy/localized room states into the report's canonical buckets."""
    status = str(value or "available").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "checked_in": "occupied",
        "dolu": "occupied",
        "in_house": "occupied",
        "kirli": "dirty",
        "cleaning": "dirty",
        "temizlikte": "dirty",
        "repair": "maintenance",
        "bakim": "maintenance",
        "bakım": "maintenance",
        "blocked": "out_of_order",
        "ooo": "out_of_order",
        "sale_closed": "out_of_order",
        "clean": "available",
        "inspected": "available",
        "ready": "available",
        "bos": "available",
        "boş": "available",
    }
    return aliases.get(
        status,
        status if status in {"available", "occupied", "dirty", "maintenance", "out_of_order"} else "out_of_order",
    )


def _normalized_nationality(value) -> str:
    """Return one human-readable bucket for common country aliases.

    Guest imports may contain ISO-2, ISO-3, Turkish/English names or arbitrary
    casing.  Reports must not count the same nationality as several countries.
    """
    raw = " ".join(str(value or "").strip().split())
    if not raw:
        return "Belirtilmemiş"
    key = "".join(
        char for char in unicodedata.normalize("NFKD", raw.casefold())
        if not unicodedata.combining(char)
    ).replace("ı", "i").replace(".", "")
    aliases = {
        "tr": "Türkiye", "tur": "Türkiye", "turkiye": "Türkiye", "turkey": "Türkiye",
        "sa": "Suudi Arabistan", "sau": "Suudi Arabistan", "saudi arabia": "Suudi Arabistan", "suudi arabistan": "Suudi Arabistan",
        "cn": "Çin", "chn": "Çin", "china": "Çin", "cin": "Çin",
        "il": "İsrail", "isr": "İsrail", "israel": "İsrail", "israil": "İsrail",
        "ch": "İsviçre", "che": "İsviçre", "switzerland": "İsviçre", "isvicre": "İsviçre",
    }
    return aliases.get(key, raw.upper() if len(raw) in {2, 3} else raw.title())


def _normalized_room_type(value) -> str:
    """Normalize known legacy room-type spelling variants for reporting only."""
    raw = " ".join(str(value or "Standart").strip().split())
    folded = "".join(
        char for char in unicodedata.normalize("NFKD", raw.casefold())
        if not unicodedata.combining(char)
    ).replace("ı", "i")
    key = re.sub(r"[^\w]+", "", folded)
    aliases = {
        "standard": "Standart",
        "standart": "Standart",
        "jakuziliagacev": "Jakuzili ağaç ev",
        "jakuzisizagacev": "Jakuzisiz ağaç ev",
        "dublexagacev": "Dubleks ağaç ev",
        "dubleksagacev": "Dubleks ağaç ev",
        "suitodajakuzilivesomineli": "Jakuzili ve şömineli süit",
        "suitodaoturmaodasijakuzisomine": "Jakuzili ve şömineli süit",
    }
    return aliases.get(key, raw)


def _date_part(value) -> str:
    """Return the ISO calendar date for date-only and datetime values."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date_type)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)[:10]


def _booking_occupied_on(booking: dict, target_date: str) -> bool:
    """Whether a booking represents an actual occupied room-night.

    Hotel stays use a half-open interval: arrival is included, departure is not.
    Confirmed bookings are arrivals, not in-house guests. Historical checked-out
    bookings remain visible for the nights they actually occupied the room.
    """
    status = str(booking.get("status") or "").lower()
    if status not in IN_HOUSE_STATUSES:
        return False
    check_in = _date_part(booking.get("check_in"))
    check_out = _date_part(booking.get("check_out"))
    if not check_in or not check_out or not (check_in <= target_date < check_out):
        return False

    # ``checked_in_at`` is a wall-clock audit timestamp. It must not be used as
    # the hotel calendar date: a property can legitimately operate on an older
    # PMS business date (for example after an interrupted night audit). In that
    # case comparing its real timestamp with ``target_date`` hides a guest who
    # is visibly checked in. The scheduled stay plus checked-in status is the
    # canonical occupancy interval; an actual checkout can still shorten it.
    actual_out = _date_part(booking.get("checked_out_at"))
    if actual_out and target_date >= actual_out:
        return False
    return True


def _guest_display_name(guest: dict | None, booking: dict) -> str:
    if guest:
        name = guest.get("name") or f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
        if name:
            return str(name).strip()
    return str(booking.get("guest_name") or booking.get("primary_guest_name") or "Misafir bilgisi eksik").strip()


def _guest_identity(guest: dict | None, booking: dict) -> tuple[str | None, str | None]:
    guest = guest or {}
    national_id = (
        guest.get("national_id")
        or guest.get("tc_identity_number")
        or guest.get("identity_number")
        or guest.get("id_number")
        or booking.get("national_id")
        or booking.get("tc_identity_number")
        or booking.get("id_number")
    )
    passport = guest.get("passport_number") or booking.get("passport_number")
    if str(guest.get("id_type") or "").lower() == "passport" and not passport:
        passport = guest.get("id_number")
    return national_id, passport


def _payment_method(payment: dict) -> str:
    return str(payment.get("payment_method") or payment.get("method") or "other").strip().lower()


def _payment_is_effective(payment: dict) -> bool:
    status = str(payment.get("status") or "paid").strip().lower()
    return not payment.get("voided") and status not in {"void", "voided", "failed", "cancelled", "rejected"}


def _payment_is_collection(payment: dict) -> bool:
    """Return whether a payment row represents money actually collected.

    Discounts, complimentary stays and city-ledger transfers settle a folio but
    never enter a physical/virtual cashier.  Mixing those rows into the cash
    movements table made its row total disagree with the front-cashier cards.
    """
    return _payment_is_effective(payment) and _payment_method(payment) not in NON_CASH_PAYMENT_METHODS


def _nightly_booking_rate(booking: dict, target_day: str, daily_rate: dict | None = None) -> float:
    """Resolve the agreed nightly price without falling back to room rack rate."""
    if daily_rate and daily_rate.get("rate") is not None:
        return round(float(daily_rate.get("rate") or 0), 2)
    if booking.get("base_rate") is not None:
        return round(float(booking.get("base_rate") or 0), 2)
    check_in = _date_part(booking.get("check_in"))
    check_out = _date_part(booking.get("check_out"))
    try:
        nights = max(1, (datetime.fromisoformat(check_out) - datetime.fromisoformat(check_in)).days)
    except (TypeError, ValueError):
        nights = 1
    return round(float(booking.get("total_amount") or 0) / nights, 2)


def _allocated_booking_revenue(booking: dict) -> float:
    """Return the accounting value allocated to one booked night.

    ``base_rate`` is a pricing reference and can remain higher than the final
    agreed reservation total after a manual price change.  Revenue reports must
    allocate the final reservation total, otherwise the currency breakdown and
    the scalar period total describe different money.
    """
    if booking.get("is_complimentary"):
        return 0.0
    check_in = _date_part(booking.get("check_in"))
    check_out = _date_part(booking.get("check_out"))
    try:
        nights = max(1, (datetime.fromisoformat(check_out) - datetime.fromisoformat(check_in)).days)
    except (TypeError, ValueError):
        nights = 1
    return round(float(booking.get("total_amount") or 0) / nights, 2)


def _complimentary_night_info(
    booking: dict,
    target_day: str,
    daily_rate: dict | None = None,
    payments: list[dict] | None = None,
) -> dict:
    """Describe whether the selected room-night is complimentary.

    A whole-stay Comp applies to every night. Partial Comp applies either to a
    zeroed open-night rate or to an immutable closed night named by the
    financial adjustment. Keeping this decision server-side makes the screen,
    print view and CSV export use the same accounting meaning.
    """
    daily_rate = daily_rate or {}
    payments = payments or []
    adjusted_closed_night = any(
        payment.get("payment_type") == "comp_adjustment"
        and target_day in {str(value)[:10] for value in (payment.get("comp_dates") or [])}
        for payment in payments
    )
    is_comp = bool(
        booking.get("is_complimentary")
        or daily_rate.get("is_complimentary")
        or adjusted_closed_night
    )
    return {
        "is_complimentary_night": is_comp,
        "complimentary_reason": (
            daily_rate.get("complimentary_reason")
            or booking.get("complimentary_reason")
            or None
        ) if is_comp else None,
        "complimentary_mode": booking.get("complimentary_mode") if is_comp else None,
    }


def _guest_link_active_on(link: dict, target_date: str) -> bool:
    checkout_date = _date_part(link.get("checkout_date"))
    return not checkout_date or checkout_date > target_date


def _period_performance(metric_rows: list[dict], room_charges_by_day: dict[str, float]) -> dict:
    """Build one internally consistent occupancy/ADR/RevPAR period.

    Financial postings are authoritative only when every occupied day in the
    requested period has a room posting.  Before night audit, the current day
    commonly has no posting yet; returning zero ADR in that case is misleading,
    so the canonical accrued room-night revenue is used until posting completes.
    """
    occupied_room_nights = sum(int(row.get("occupied_rooms") or 0) for row in metric_rows)
    sold_room_nights = sum(int(row.get("sold_rooms", row.get("occupied_rooms")) or 0) for row in metric_rows)
    available_room_nights = sum(int(row.get("total_rooms") or 0) for row in metric_rows)
    accrued_room_revenue = round(sum(float(row.get("revenue") or 0) for row in metric_rows), 2)
    posted_room_revenue = round(sum(float(room_charges_by_day.get(str(row.get("date")), 0) or 0) for row in metric_rows), 2)
    posting_gap_days = [
        str(row.get("date"))
        for row in metric_rows
        if int(row.get("occupied_rooms") or 0) > 0
        and float(room_charges_by_day.get(str(row.get("date")), 0) or 0) == 0
    ]
    use_posted = bool(occupied_room_nights) and not posting_gap_days
    room_revenue = posted_room_revenue if use_posted else accrued_room_revenue
    return {
        "start_date": str(metric_rows[0].get("date")) if metric_rows else None,
        "end_date": str(metric_rows[-1].get("date")) if metric_rows else None,
        "occupied_room_nights": occupied_room_nights,
        "sold_room_nights": sold_room_nights,
        "available_room_nights": available_room_nights,
        "occupancy_percentage": round(occupied_room_nights / available_room_nights * 100, 2) if available_room_nights else 0,
        "posted_room_revenue": posted_room_revenue,
        "accrued_room_revenue": accrued_room_revenue,
        "room_revenue": round(room_revenue, 2),
        "revenue_source": "posted" if use_posted else "accrued",
        "posting_gap_days": posting_gap_days,
        "adr": round(room_revenue / sold_room_nights, 2) if sold_room_nights else 0,
        "revpar": round(room_revenue / available_room_nights, 2) if available_room_nights else 0,
    }


@sub_router.get("/reports/official-guest-list")
async def get_official_guest_list(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _permission: None = Depends(require_op("view_guest_list")),
):
    """Resmi misafir listesi (Maliye / resmi denetimler için).

    Verilen tarihte (veya PMS iş tarihinde) otelde konaklayan tüm misafirleri ve
    konaklama bilgilerini döner. Konaklama aralığı [giriş, çıkış) şeklindedir.
    """
    if date:
        try:
            target_date = datetime.fromisoformat(date).date()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Geçersiz rapor tarihi") from exc
    else:
        business_date_state = await ensure_business_date_initialized(db, current_user.tenant_id)
        target_date = date_type.fromisoformat(str(business_date_state["business_date"])[:10])
    from security.guest_data_visibility import guest_visibility_summary, protect_guest_row

    # Stays are [check-in, check-out): a departure date is not another room-night.
    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
    next_day = day_start + timedelta(days=1)

    # İlgili tarihte otelde konaklayan rezervasyonlar
    day_start_iso = day_start.date().isoformat()
    next_day_iso = next_day.date().isoformat()
    bookings_cursor = db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "status": {"$nin": ["cancelled", "no_show"]},
            "$or": [
                {"check_in": {"$lt": next_day_iso}, "check_out": {"$gt": day_start_iso}},
                {"check_in": {"$lt": next_day}, "check_out": {"$gt": day_start}},
                {"check_in": {"$lt": next_day_iso}, "check_out": {"$gt": day_start}},
                {"check_in": {"$lt": next_day}, "check_out": {"$gt": day_start_iso}},
            ],
        },
        {
            "_id": 0,
            "id": 1,
            "guest_id": 1,
            "primary_guest_name": 1,
            "guest_name": 1,
            "room_number": 1,
            "room_id": 1,
            "id_number": 1,
            "passport_number": 1,
            "check_in": 1,
            "check_out": 1,
            "checked_in_at": 1,
            "checked_out_at": 1,
            "adults": 1,
            "children": 1,
            "total_amount": 1,
            "currency": 1,
            "billing_tax_number": 1,
            "billing_address": 1,
            "company_id": 1,
            "market_segment": 1,
        },
    )

    bookings = [
        booking
        for booking in await bookings_cursor.to_list(None)
        if _booking_occupied_on(booking, target_date.isoformat())
    ]

    # Fetch rooms to map room_id to room_number for official report
    room_ids = list({b.get("room_id") for b in bookings if b.get("room_id")})
    room_map = {}
    if room_ids:
        rooms = await db.rooms.find(
            {"tenant_id": current_user.tenant_id, "id": {"$in": room_ids}},
            {"_id": 0, "id": 1, "room_number": 1, "room_no": 1, "name": 1}
        ).to_list(None)
        for r in rooms:
            room_map[str(r.get("id"))] = str(r.get("room_number") or r.get("room_no") or r.get("name") or "?").strip()

    booking_ids = [b.get("id") for b in bookings if b.get("id")]
    guest_links = await db.booking_guests.find(
        {"tenant_id": current_user.tenant_id, "booking_id": {"$in": booking_ids}},
        {"_id": 0},
    ).to_list(None) if booking_ids else []

    links_by_booking: dict[str, list[dict]] = {}
    for link in guest_links:
        links_by_booking.setdefault(str(link.get("booking_id")), []).append(link)

    # Primary and additional occupants must all appear in the official list.
    guest_ids = {str(b["guest_id"]) for b in bookings if b.get("guest_id")}
    guest_ids.update(str(link["guest_id"]) for link in guest_links if link.get("guest_id"))

    guests_by_id = {}
    if guest_ids:
        guests_cursor = db.guests.find(
            {"tenant_id": current_user.tenant_id, "id": {"$in": list(guest_ids)}},
            {
                "_id": 0,
                "id": 1,
                "first_name": 1,
                "last_name": 1,
                "name": 1,
                "national_id": 1,
                "tc_identity_number": 1,
                "identity_number": 1,
                "id_number": 1,
                "id_type": 1,
                "passport_number": 1,
                "country": 1,
                "nationality": 1,
                "city": 1,
                "date_of_birth": 1,
                "birth_date": 1,
            },
        )
        from security.encrypted_lookup import decrypt_guest_doc

        guest_docs = [decrypt_guest_doc(g) for g in await guests_cursor.to_list(None)]
        guests_by_id = {str(g["id"]): g for g in guest_docs}

    rows = []
    for b in bookings:
        occupant_ids = []
        if b.get("guest_id"):
            occupant_ids.append(str(b["guest_id"]))
        occupant_ids.extend(
            str(link["guest_id"])
            for link in links_by_booking.get(str(b.get("id")), [])
            if link.get("guest_id") and _guest_link_active_on(link, target_date.isoformat())
        )
        occupant_ids = list(dict.fromkeys(occupant_ids))

        # Legacy bookings without a guest document still produce one explicit row.
        occupants = [(guest_id, guests_by_id.get(guest_id)) for guest_id in occupant_ids] or [(None, None)]
        for occupant_index, (guest_id, guest) in enumerate(occupants):
            national_id, passport_number = _guest_identity(guest, b if occupant_index == 0 else {})
            rows.append(
                protect_guest_row({
                    "id": f"{b.get('id')}:{guest_id or occupant_index}",
                    "booking_id": b.get("id"),
                    "guest_id": guest_id,
                    "guest_name": _guest_display_name(guest, b if occupant_index == 0 else {}),
                    "national_id": national_id,
                    "passport_number": passport_number,
                    "country": (guest or {}).get("country") or (guest or {}).get("nationality"),
                    "city": (guest or {}).get("city"),
                    "date_of_birth": (guest or {}).get("date_of_birth") or (guest or {}).get("birth_date"),
                    "room_number": str(b.get("room_number") or room_map.get(str(b.get("room_id"))) or "?").strip() or "?",
                    "check_in": b.get("check_in"),
                    "check_out": b.get("check_out"),
                    "adults": b.get("adults", 1) if occupant_index == 0 else 0,
                    "children": b.get("children", 0) if occupant_index == 0 else 0,
                    "reservation_adults": b.get("adults", 1),
                    "reservation_children": b.get("children", 0),
                    "total_amount": b.get("total_amount", 0.0) if occupant_index == 0 else 0.0,
                    "currency": b.get("currency") or "TRY",
                    "billing_tax_number": b.get("billing_tax_number"),
                    "billing_address": b.get("billing_address"),
                    "company_id": b.get("company_id"),
                    "market_segment": b.get("market_segment"),
                }, current_user)
            )

    return {
        "date": target_date.isoformat(),
        "count": len(rows),
        "rows": rows,
        "privacy": guest_visibility_summary(current_user),
    }


def _user_has_pii_access(user) -> bool:
    """KVKK PII gate: TCKN / pasaport sadece yöneticilere açıktır.

    - Admin / Super-Admin / Manager / General Manager rolleri: tam erişim.
    - Diğer roller: yalnızca `granted_permissions` içinde "view_guest_pii"
      anahtarı bulunan kullanıcılar PII alanlarını görebilir.
    """
    role = getattr(user, "role", None)
    role_str = getattr(role, "value", None) or str(role or "")
    if role_str in ("admin", "super_admin", "manager", "general_manager"):
        return True
    granted = getattr(user, "granted_permissions", None) or []
    return "view_guest_pii" in granted


def _mask_pii(value):
    if not value:
        return value
    s = str(value)
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


@sub_router.get("/reports/basic-dashboard")
async def get_basic_reports_dashboard(
    date: str = None,
    period: str = "monthly",
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("basic_reporting")),
):
    """
    Temel Raporlar Dashboard - OPTIMIZED: Batch queries + cache (Tur 28).
    """
    if period not in {"daily", "monthly"}:
        raise HTTPException(status_code=422, detail="Geçersiz rapor dönemi")
    if date:
        try:
            datetime.fromisoformat(date[:10])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Geçersiz rapor tarihi") from exc
    else:
        business_date_state = await ensure_business_date_initialized(db, current_user.tenant_id)
        date = str(business_date_state["business_date"])[:10]
    # Cache the complete tenant-scoped report, then apply the current user's
    # field policy outside the cache.  This prevents one employee's unmasked
    # response from ever being reused for another employee.
    result = await _basic_dashboard_impl(current_user, True, date, period)
    from copy import deepcopy

    from security.guest_data_visibility import guest_visibility_summary, protect_guest_row

    result = deepcopy(result)
    result["guest_list"] = [protect_guest_row(row, current_user) for row in result.get("guest_list", [])]
    result["daily_lists"] = {
        key: [protect_guest_row(row, current_user) for row in rows]
        for key, rows in (result.get("daily_lists") or {}).items()
    }
    if isinstance(result.get("payments"), dict):
        result["payments"]["rows"] = [protect_guest_row(row, current_user) for row in result["payments"].get("rows", [])]
    if isinstance(result.get("housekeeping"), dict):
        result["housekeeping"]["rows"] = [protect_guest_row(row, current_user) for row in result["housekeeping"].get("rows", [])]
    result["room_rate_control"] = [protect_guest_row(row, current_user) for row in result.get("room_rate_control", [])]
    result["privacy"] = guest_visibility_summary(current_user)
    return result


@cached(ttl=120, key_prefix="reports_basic_dashboard_v2", role_aware=True)
async def _basic_dashboard_impl(current_user: User, has_pii: bool, target_date: str, period: str = "monthly"):
    today = datetime.fromisoformat(target_date[:10]).replace(tzinfo=UTC)
    today_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today.replace(hour=23, minute=59, second=59)
    next_day = today_start + timedelta(days=1)
    target_day = today_start.date().isoformat()
    tenant_id = current_user.tenant_id
    if period == "daily":
        month_start = today_start
        trend_start = today_start
        week_start = today_start
        previous_start = today_start - timedelta(days=1)
        previous_end = today_start
        last_year_start = today_start - timedelta(days=365)
        last_year_end = last_year_start + timedelta(days=1)
    else:
        month_start = (today - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = (today - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        trend_start = (today - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        previous_start = trend_start - timedelta(days=30)
        previous_end = trend_start
        last_year_start = trend_start - timedelta(days=365)
        last_year_end = today_start - timedelta(days=364)

    charge_range_start = min(last_year_start, previous_start, trend_start).date().isoformat()
    charge_range_start_dt = datetime.fromisoformat(charge_range_start).replace(tzinfo=UTC)

    # ALL queries in parallel
    async def get_fnb_orders():
        # Never convert a database/query failure into a believable "0 TL".
        # An incomplete financial report is more dangerous than a visible error.
        return await db.pos_orders.find(
            {
                "tenant_id": tenant_id,
                "status": {"$nin": ["cancelled", "canceled", "void", "voided"]},
                **accounting_period_match(
                    charge_range_start,
                    target_day,
                    {"closed_at": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                    {"created_at": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                ),
            },
            {
                "_id": 0,
                "id": 1,
                "business_date": 1,
                "closed_at": 1,
                "created_at": 1,
                "total_amount": 1,
                "grand_total": 1,
                "currency": 1,
                "status": 1,
                "payment_status": 1,
            },
        ).to_list(5000)

    results = await asyncio.gather(
        db.rooms.find({"tenant_id": tenant_id}).to_list(1000),
        db.bookings.find(
            {
                "tenant_id": tenant_id,
                "$or": [
                    {"check_in": {"$gte": trend_start.date().isoformat(), "$lt": next_day.date().isoformat()}},
                    {"check_in": {"$gte": trend_start, "$lt": next_day}},
                    {"check_out": {"$gte": trend_start.date().isoformat(), "$lt": next_day.date().isoformat()}},
                    {"check_out": {"$gte": trend_start, "$lt": next_day}},
                    {"check_in": {"$lt": trend_start.date().isoformat()}, "check_out": {"$gt": target_day}},
                    {"check_in": {"$lt": trend_start}, "check_out": {"$gt": today_start}},
                    {"status": "cancelled", "cancelled_at": {"$gte": trend_start.isoformat(), "$lt": next_day.isoformat()}},
                    {"status": "cancelled", "cancelled_at": {"$gte": trend_start, "$lt": next_day}},
                    {"status": "cancelled", "updated_at": {"$gte": trend_start.isoformat(), "$lt": next_day.isoformat()}},
                    {"status": "cancelled", "updated_at": {"$gte": trend_start, "$lt": next_day}},
                ],
            },
            {
                "_id": 0,
                "check_in": 1,
                "check_out": 1,
                "total_amount": 1,
                "currency": 1,
                "status": 1,
                "booking_source": 1,
                "room_type": 1,
                "created_at": 1,
                "updated_at": 1,
                "cancelled_at": 1,
                "id": 1,
                "guest_id": 1,
                "guest_name": 1,
                "guest_email": 1,
                "guest_phone": 1,
                "room_number": 1,
                "room_id": 1,
                "nationality": 1,
                "id_number": 1,
                "passport_number": 1,
                "checked_in_at": 1,
                "checked_out_at": 1,
                "adults": 1,
                "children": 1,
                "base_rate": 1,
                "is_complimentary": 1,
                "is_partially_complimentary": 1,
                "complimentary_mode": 1,
                "complimentary_scope": 1,
                "complimentary_reason": 1,
                "complimentary_original_total": 1,
            },
        ).to_list(10000),
        db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "check_in": {"$lt": next_day.date().isoformat()},
                "check_out": {"$gt": target_day},
                "status": {"$in": list(IN_HOUSE_STATUSES)},
            }
        ),
        db.housekeeping_tasks.find(
            {
                "tenant_id": tenant_id,
                "$or": [
                    {"created_at": {"$gte": today_start.isoformat(), "$lt": next_day.isoformat()}},
                    {"started_at": {"$gte": today_start.isoformat(), "$lt": next_day.isoformat()}},
                    {"completed_at": {"$gte": today_start.isoformat(), "$lt": next_day.isoformat()}},
                    {"scheduled_date": target_day},
                    {
                        "status": {"$in": ["pending", "assigned", "open", "in_progress", "inprogress", "active"]},
                        "created_at": {"$lt": next_day.isoformat()},
                    },
                ],
            }
        ).to_list(5000),
        db.maintenance_tasks.count_documents({"tenant_id": tenant_id, "status": {"$in": ["open", "in_progress", "pending"]}}),
        db.maintenance_tasks.count_documents({"tenant_id": tenant_id, "status": "completed", "completed_at": {"$gte": month_start.isoformat(), "$lte": today_end.isoformat()}}),
        db.invoices.count_documents({"tenant_id": tenant_id, "payment_status": {"$in": ["pending", "partial"]}}),
        db.invoices.count_documents({"tenant_id": tenant_id, "payment_status": "paid", "created_at": {"$gte": month_start.isoformat(), "$lte": today_end.isoformat()}}),
        db.guests.find(
            {"tenant_id": tenant_id},
            {
                "_id": 0,
                "id": 1,
                "name": 1,
                "first_name": 1,
                "last_name": 1,
                "email": 1,
                "phone": 1,
                "nationality": 1,
                "country": 1,
                "city": 1,
                "national_id": 1,
                "tc_identity_number": 1,
                "identity_number": 1,
                "id_number": 1,
                "id_type": 1,
                "passport_number": 1,
            },
        ).to_list(10000),
        db.payments.find(
            {
                "tenant_id": tenant_id,
                **accounting_day_match(
                    target_day,
                    {"processed_at": {"$regex": f"^{target_day}"}},
                    {"payment_date": target_day},
                    {"date": target_day},
                    {"created_at": {"$regex": f"^{target_day}"}},
                    {"created_at": {"$gte": today_start.isoformat(), "$lt": next_day.isoformat()}},
                ),
            },
            {"_id": 0},
        ).to_list(10000),
        db.bookings.find(
            {
                "tenant_id": tenant_id,
                "$or": [
                    {"check_in": {"$gte": previous_start.date().isoformat(), "$lt": previous_end.date().isoformat()}},
                    {"check_in": {"$gte": previous_start, "$lt": previous_end}},
                ],
                "status": {"$in": ["confirmed", "checked_in", "checked_out"]},
            },
            {"_id": 0, "total_amount": 1, "check_in": 1, "check_out": 1},
        ).to_list(10000),
        db.bookings.find(
            {
                "tenant_id": tenant_id,
                "$or": [
                    {"check_in": {"$gte": last_year_start.date().isoformat(), "$lt": last_year_end.date().isoformat()}},
                    {"check_in": {"$gte": last_year_start, "$lt": last_year_end}},
                ],
                "status": {"$in": ["confirmed", "checked_in", "checked_out"]},
            },
            {"_id": 0, "total_amount": 1, "check_in": 1, "check_out": 1},
        ).to_list(10000),
        db.room_blocks.find(
            {
                "tenant_id": tenant_id,
                "status": "active",
                "allow_sell": {"$ne": True},
                "start_date": {"$lt": next_day.date().isoformat()},
                "$or": [{"end_date": {"$gt": trend_start.date().isoformat()}}, {"end_date": None}],
            },
            {"_id": 0, "room_id": 1, "start_date": 1, "end_date": 1, "status": 1, "allow_sell": 1},
        ).to_list(10000),
        get_fnb_orders(),
    )
    rooms, all_bk, in_house, hk_tasks, maint_open, maint_completed, pending_invoices, paid_invoices, all_guests, all_payments, prev_bookings, ly_bookings, room_blocks, fnb_orders = results

    loaded_booking_ids = {str(booking.get("id")) for booking in all_bk if booking.get("id")}
    missing_payment_booking_ids = list(
        {
            str(payment.get("booking_id"))
            for payment in all_payments
            if payment.get("booking_id") and str(payment.get("booking_id")) not in loaded_booking_ids
        }
    )
    payment_only_bookings = (
        await db.bookings.find(
            {"tenant_id": tenant_id, "id": {"$in": missing_payment_booking_ids}},
            {"_id": 0, "id": 1, "room_id": 1, "room_number": 1, "guest_id": 1, "guest_name": 1, "primary_guest_name": 1},
        ).to_list(10000)
        if missing_payment_booking_ids
        else []
    )

    booking_ids = [str(booking.get("id")) for booking in all_bk if booking.get("id")]
    daily_rate_rows = (
        await db.daily_rates.find(
            {
                "tenant_id": tenant_id,
                "booking_id": {"$in": booking_ids},
                "date": target_day,
            },
            {
                "_id": 0,
                "booking_id": 1,
                "date": 1,
                "rate": 1,
                "is_complimentary": 1,
                "complimentary_reason": 1,
            },
        ).to_list(10000)
        if booking_ids
        else []
    )
    daily_rates_by_booking = {str(row.get("booking_id")): row for row in daily_rate_rows}
    booking_payment_rows = (
        await db.payments.find(
            {
                "tenant_id": tenant_id,
                "booking_id": {"$in": booking_ids},
                "voided": {"$ne": True},
            },
            {
                "_id": 0,
                "booking_id": 1,
                "amount": 1,
                "currency": 1,
                "received_amount": 1,
                "received_currency": 1,
                "notes": 1,
                "method": 1,
                "payment_method": 1,
                "payment_type": 1,
                "status": 1,
                "voided": 1,
                "comp_dates": 1,
            },
        ).to_list(20000)
        if booking_ids
        else []
    )
    received_payments_by_booking: dict[str, list[dict]] = {}
    payments_by_booking: dict[str, list[dict]] = {}
    booking_currency_by_id = {
        str(booking.get("id")): str(booking.get("currency") or "TRY").upper()
        for booking in all_bk
        if booking.get("id")
    }
    for payment in booking_payment_rows:
        booking_id = str(payment.get("booking_id") or "")
        payments_by_booking.setdefault(booking_id, []).append(payment)
        if not _payment_is_collection(payment):
            continue
        received = _received_payment_amount(payment, booking_currency_by_id.get(booking_id, "TRY"))
        if received["amount"] > 0:
            received_payments_by_booking.setdefault(booking_id, []).append(received)

    currency_exchanges = await db.currency_exchanges.find(
        {"tenant_id": tenant_id, "business_date": target_day, "status": "posted"},
        {"_id": 0},
    ).sort("created_at", 1).to_list(10000)

    period_charges = await db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            **accounting_period_match(
                charge_range_start,
                target_day,
                {"date": {"$gte": charge_range_start, "$lt": next_day.date().isoformat()}},
                {"date": {"$gte": charge_range_start_dt, "$lt": next_day}},
                {"date": {"$exists": False}, "created_at": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                {"date": {"$exists": False}, "created_at": {"$gte": charge_range_start_dt, "$lt": next_day}},
            ),
        },
        {
            "_id": 0,
            "id": 1,
            "business_date": 1,
            "date": 1,
            "created_at": 1,
            "total": 1,
            "amount": 1,
            "charge_category": 1,
            "charge_type": 1,
            "booking_id": 1,
            "currency": 1,
            "source_pos_order_id": 1,
        },
    ).to_list(50000)
    period_charges = [
        {**row, "date": row.get("business_date") or row.get("date") or row.get("created_at")}
        for row in period_charges
    ]

    # Reservation-card extras live in ``extra_charges`` until they are moved to
    # a folio.  Reports previously ignored that collection entirely, which made
    # room-posted coffee/minibar/etc. disappear from both revenue and F&B.
    extra_charge_rows = await db.extra_charges.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            **accounting_period_match(
                charge_range_start,
                target_day,
                {"charge_date": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                {"charge_date": {"$gte": charge_range_start_dt, "$lt": next_day}},
                {"date": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                {"date": {"$gte": charge_range_start_dt, "$lt": next_day}},
                {"created_at": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                {"created_at": {"$gte": charge_range_start_dt, "$lt": next_day}},
            ),
        },
        {
            "_id": 0,
            "id": 1,
            "business_date": 1,
            "charge_date": 1,
            "date": 1,
            "created_at": 1,
            "total": 1,
            "charge_amount": 1,
            "amount": 1,
            "category": 1,
            "charge_category": 1,
            "charge_type": 1,
            "booking_id": 1,
            "currency": 1,
        },
    ).to_list(20000)
    period_charges.extend(
        {
            **row,
            "date": row.get("business_date") or row.get("charge_date") or row.get("date") or row.get("created_at"),
            "total": row.get("total") if row.get("total") is not None else row.get("charge_amount", row.get("amount", 0)),
            "charge_category": row.get("charge_category") or row.get("category") or row.get("charge_type") or "extra",
            "_source": "extra_charge",
        }
        for row in extra_charge_rows
    )
    represented_pos_order_ids = {
        str(charge.get("source_pos_order_id"))
        for charge in period_charges
        if charge.get("source_pos_order_id")
    }
    period_charges.extend(
        {
            "id": f"pos:{order.get('id')}",
            "date": order.get("business_date") or order.get("closed_at") or order.get("created_at"),
            "total": order.get("total_amount") or order.get("grand_total") or 0,
            "charge_category": "fnb",
            "source_pos_order_id": order.get("id"),
            "currency": order.get("currency") or "TRY",
            "_source": "direct_pos",
        }
        for order in fnb_orders
        if str(order.get("id") or "") not in represented_pos_order_ids
        and str(order.get("status") or "").lower() in {"closed", "completed", "served", "paid"}
    )

    def charge_amount(charge: dict) -> float:
        return float(charge.get("total") or charge.get("amount") or 0)

    def charge_currency(charge: dict) -> str:
        booking = booking_currency_by_id.get(str(charge.get("booking_id") or ""))
        return _currency_code(charge.get("currency"), booking or "TRY")

    def charges_between(start: datetime, end_exclusive: datetime) -> list[dict]:
        start_key, end_key = start.date().isoformat(), end_exclusive.date().isoformat()
        return [charge for charge in period_charges if start_key <= _date_part(charge.get("business_date") or charge.get("date")) < end_key]

    # FIX: Room Mapping
    room_map = {}
    for r in rooms:
        room_map[str(r.get("id"))] = r.get("room_number") or r.get("room_no") or r.get("name") or "?"

    from security.encrypted_lookup import decrypt_guest_doc

    all_guests = [decrypt_guest_doc(g) for g in all_guests]
    guests_by_id = {str(g.get("id")): g for g in all_guests if g.get("id")}

    booking_ids = [b.get("id") for b in all_bk if b.get("id")]
    guest_links = (
        await db.booking_guests.find(
            {"tenant_id": tenant_id, "booking_id": {"$in": booking_ids}},
            {"_id": 0},
        ).to_list(20000)
        if booking_ids
        else []
    )
    links_by_booking: dict[str, list[dict]] = {}
    for link in guest_links:
        links_by_booking.setdefault(str(link.get("booking_id")), []).append(link)

    def booking_guest_rows(booking: dict, include_additional: bool = True) -> list[dict]:
        guest_ids = []
        if booking.get("guest_id"):
            guest_ids.append(str(booking["guest_id"]))
        if include_additional:
            guest_ids.extend(
                str(link["guest_id"])
                for link in links_by_booking.get(str(booking.get("id")), [])
                if link.get("guest_id") and _guest_link_active_on(link, target_day)
            )
        guest_ids = list(dict.fromkeys(guest_ids))
        occupants = [(guest_id, guests_by_id.get(guest_id)) for guest_id in guest_ids] or [(None, None)]
        booking_id = str(booking.get("id"))
        daily_rate = daily_rates_by_booking.get(booking_id)
        nightly_rate = _nightly_booking_rate(booking, target_day, daily_rate)
        comp_info = _complimentary_night_info(
            booking,
            target_day,
            daily_rate,
            payments_by_booking.get(booking_id),
        )
        rows = []
        for index, (guest_id, guest) in enumerate(occupants):
            identity, passport = _guest_identity(guest, booking if index == 0 else {})
            rows.append(
                {
                    "id": f"{booking.get('id')}:{guest_id or index}",
                    "booking_id": booking.get("id"),
                    "guest_id": guest_id,
                    "guest_name": _guest_display_name(guest, booking if index == 0 else {}),
                    "guest_email": (guest or {}).get("email") or (booking.get("guest_email") if index == 0 else None),
                    "guest_phone": (guest or {}).get("phone") or (booking.get("guest_phone") if index == 0 else None),
                    "room_number": str(booking.get("room_number") or room_map.get(str(booking.get("room_id"))) or "?").strip() or "?",
                    "room_type": booking.get("room_type"),
                    "check_in": booking.get("check_in"),
                    "check_out": booking.get("check_out"),
                    "checked_in_at": booking.get("checked_in_at"),
                    "checked_out_at": booking.get("checked_out_at"),
                    "total_amount": booking.get("total_amount", 0) if index == 0 else 0,
                    "currency": booking.get("currency") or "TRY",
                    # A room charge belongs to the stay, not to every occupant.
                    # Keep it on the primary row so multi-guest rooms do not look
                    # like they generated the same revenue more than once.
                    "nightly_rate": nightly_rate if index == 0 else None,
                    "guest_nightly_charge": (0.0 if comp_info["is_complimentary_night"] else nightly_rate) if index == 0 else None,
                    "reference_nightly_rate": nightly_rate if comp_info["is_complimentary_night"] and index == 0 else None,
                    **comp_info,
                    "received_payments": received_payments_by_booking.get(str(booking.get("id")), []) if index == 0 else [],
                    "status": booking.get("status"),
                    "nationality": (guest or {}).get("nationality") or (guest or {}).get("country") or booking.get("nationality"),
                    "id_number": identity if has_pii else _mask_pii(identity),
                    "passport_number": passport if has_pii else _mask_pii(passport),
                    "booking_source": booking.get("booking_source"),
                    "is_primary": index == 0,
                    "occupant_count": len(occupants),
                }
            )
        return rows

    active_rooms = [room for room in rooms if room.get("is_active") is not False]
    total_rooms = len(active_rooms)
    room_types = {}
    for r in active_rooms:
        rt = _normalized_room_type(r.get("room_type"))
        room_types[rt] = room_types.get(rt, 0) + 1

    room_status_counts = {"available": 0, "occupied": 0, "dirty": 0, "maintenance": 0, "out_of_order": 0}
    for r in active_rooms:
        st = _normalized_room_status(r.get("current_status", r.get("status", "available")))
        room_status_counts[st] = room_status_counts.get(st, 0) + 1

    month_day, week_day = month_start.date().isoformat(), week_start.date().isoformat()
    occupied_today = arrivals = departures = no_shows = cancellations = today_revenue = 0
    period_arrivals = period_departures = period_no_shows = period_cancellations = 0
    recent_bookings = []
    week_bookings = []
    month_bookings = []
    recent_guests_data = []
    ALL_REVENUE_STATUSES = ("confirmed", "guaranteed", "checked_in", "checked_out")

    daily_in_house = []
    daily_arrivals = []
    daily_departures = []
    for bk in all_bk:
        ci, co, status = bk.get("check_in", ""), bk.get("check_out", ""), bk.get("status", "")
        amt = bk.get("total_amount", 0) or 0
        created = str(bk.get("created_at") or "")
        ci_day, co_day = _date_part(ci), _date_part(co)
        if ci_day == target_day and status in ARRIVAL_STATUSES:
            arrivals += 1
            daily_arrivals.extend(booking_guest_rows(bk))
        if co_day == target_day and status not in ("cancelled", "no_show"):
            departures += 1
            daily_departures.extend(booking_guest_rows(bk))
        if _booking_occupied_on(bk, target_day):
            daily_in_house.extend(booking_guest_rows(bk))
        if ci_day == target_day and status == "no_show":
            no_shows += 1
        cancellation_day = _date_part(bk.get("cancelled_at") or bk.get("updated_at") or created)
        if status == "cancelled" and cancellation_day == target_day:
            cancellations += 1
        if trend_start.date().isoformat() <= ci_day <= target_day:
            if status in ARRIVAL_STATUSES:
                period_arrivals += 1
            if status == "no_show":
                period_no_shows += 1
        if trend_start.date().isoformat() <= co_day <= target_day and status not in ("cancelled", "no_show"):
            period_departures += 1
        if status == "cancelled" and trend_start.date().isoformat() <= cancellation_day <= target_day:
            period_cancellations += 1
        if month_day <= ci_day <= target_day and status in ALL_REVENUE_STATUSES:
            recent_bookings.append(bk)
        if ci_day >= week_day and status in ALL_REVENUE_STATUSES:
            week_bookings.append(bk)
        # Rapor dönemi listeleri aynı tarih tanımını kullanır. İptaller giriş
        # tarihine değil iptal hareketinin tarihine aittir.
        include_in_period_list = False
        if month_day <= ci_day <= target_day and status in (*ALL_REVENUE_STATUSES, "no_show"):
            include_in_period_list = True
            if status in ALL_REVENUE_STATUSES:
                month_bookings.append(bk)
        elif status == "cancelled" and month_day <= cancellation_day <= target_day:
            include_in_period_list = True
        if include_in_period_list:
            recent_guests_data.extend(booking_guest_rows(bk))

    # Summary uses occupied rooms, while lists contain every occupant.
    in_house_room_count = len({row["room_number"] for row in daily_in_house if row.get("room_number") not in (None, "?")})
    in_house = in_house_room_count

    # Dashboard dates are realised operational history, not inventory forecast.
    # Confirmed-but-never-arrived reservations must not inflate occupancy.
    metric_rows = calculate_stay_night_metrics(all_bk, active_rooms, trend_start.date(), today.date(), actual_only=True, room_blocks=room_blocks)
    today_metric = metric_rows[-1] if metric_rows else {}
    occupied_today = today_metric.get("occupied_rooms", 0)
    charges_by_day: dict[str, float] = {}
    room_charges_by_day: dict[str, float] = {}
    charges_by_day_currency: dict[str, dict[str, float]] = {}
    room_charges_by_day_currency: dict[str, dict[str, float]] = {}
    for charge in period_charges:
        charge_day = _date_part(charge.get("business_date") or charge.get("date"))
        amount = charge_amount(charge)
        charges_by_day[charge_day] = charges_by_day.get(charge_day, 0.0) + amount
        _add_currency_amount(charges_by_day_currency.setdefault(charge_day, {}), charge_currency(charge), amount)
        category = str(charge.get("charge_category") or charge.get("charge_type") or "").lower()
        if category in {"room", "accommodation", "room_charge"}:
            room_charges_by_day[charge_day] = room_charges_by_day.get(charge_day, 0.0) + amount
            _add_currency_amount(room_charges_by_day_currency.setdefault(charge_day, {}), charge_currency(charge), amount)
    accrued_room_by_day_currency: dict[str, dict[str, float]] = {}
    sold_room_nights_by_day_currency: dict[str, dict[str, float]] = {}
    for metric in metric_rows:
        day = str(metric.get("date"))
        for booking in all_bk:
            if _booking_occupied_on(booking, day):
                currency = booking.get("currency") or "TRY"
                allocated_revenue = _allocated_booking_revenue(booking)
                _add_currency_amount(
                    accrued_room_by_day_currency.setdefault(day, {}),
                    currency,
                    allocated_revenue,
                )
                if allocated_revenue > 0:
                    _add_currency_amount(
                        sold_room_nights_by_day_currency.setdefault(day, {}),
                        currency,
                        1,
                    )

    today_room_revenue = round(room_charges_by_day.get(target_day, 0.0), 2)
    daily_period_charges = charges_between(today_start, next_day)
    daily_performance = _period_performance([today_metric] if today_metric else [], room_charges_by_day)
    period_performance = _period_performance(metric_rows, room_charges_by_day)
    # Revenue cards are accounting reports: only posted, non-voided charges
    # belong here. Accrued room revenue remains available separately for
    # operational ADR/RevPAR until night audit posts the room charges.
    today_revenue = round(sum(charge_amount(charge) for charge in daily_period_charges), 2)
    today_revenue_by_currency = _currency_breakdown(daily_period_charges, charge_amount, charge_currency)
    posted_room_revenue_by_currency = _merge_currency_breakdowns(room_charges_by_day_currency.get(target_day, {}))
    accrued_room_revenue_by_currency = _merge_currency_breakdowns(accrued_room_by_day_currency.get(target_day, {}))
    # Keep the displayed currency breakdown on the exact same basis as the
    # scalar room revenue/ADR/RevPAR.  Falling back independently made one card
    # show accrued revenue while its detail rows divided posted revenue.
    today_room_revenue_by_currency = (
        posted_room_revenue_by_currency
        if daily_performance["revenue_source"] == "posted"
        else accrued_room_revenue_by_currency
    )
    fnb_revenue_by_currency = _currency_breakdown(
        [charge for charge in daily_period_charges if str(charge.get("charge_category") or charge.get("charge_type") or "").strip().lower() in FNB_CHARGE_CATEGORIES],
        charge_amount,
        charge_currency,
    )
    # Legacy scalar values are retained only when the total has one currency.
    # A numeric EUR + TRY sum is not a financial total and must never leak to
    # an API consumer that has not yet adopted the breakdown fields.
    fnb_revenue = _single_currency_amount(fnb_revenue_by_currency)
    occupancy_pct = daily_performance["occupancy_percentage"]
    adr = daily_performance["adr"]
    available_rooms_today = int(today_metric.get("total_rooms", total_rooms) or 0)
    revpar = daily_performance["revpar"]
    occupancy_trend = [
        {"date": row["date"], "label": datetime.fromisoformat(row["date"]).strftime("%d %b"), "occupancy": row["occupancy_rate"], "rooms_occupied": row["occupied_rooms"]} for row in metric_rows
    ]
    revenue_trend = []
    for row in metric_rows:
        day = row["date"]
        revenue_trend.append(
            {
                "date": day,
                "label": datetime.fromisoformat(day).strftime("%d %b"),
                "revenue": round(charges_by_day.get(day, 0.0), 2),
                "revenue_by_currency": charges_by_day_currency.get(day, {}),
            }
        )

    tasks_by_room: dict[str, list[dict]] = {}
    for task in hk_tasks:
        if task.get("room_id"):
            tasks_by_room.setdefault(str(task["room_id"]), []).append(task)
    departures_by_room = {
        str(booking.get("room_id")): booking
        for booking in all_bk
        if booking.get("room_id")
        and _date_part(booking.get("check_out")) == target_day
        and str(booking.get("status") or "").lower() not in {"cancelled", "no_show"}
    }
    housekeeping_rows = []
    for room in active_rooms:
        room_id = str(room.get("id"))
        tasks = sorted(
            tasks_by_room.get(room_id, []),
            key=lambda task: str(task.get("completed_at") or task.get("started_at") or task.get("created_at") or ""),
            reverse=True,
        )
        task = tasks[0] if tasks else {}
        departure = departures_by_room.get(room_id)
        room_status = _normalized_room_status(
            room.get("housekeeping_status") or room.get("hk_status") or room.get("status") or "available"
        )
        task_status = str(task.get("status") or task.get("task_status") or "").lower()
        departed = bool(departure and (departure.get("checked_out_at") or departure.get("status") == "checked_out"))
        housekeeping_rows.append(
            {
                "id": task.get("id") or f"room:{room_id}",
                "room_id": room_id,
                "room_number": str(room.get("room_number") or room.get("room_no") or "?").strip() or "?",
                "room_type": room.get("room_type"),
                "room_status": room_status,
                "task_type": task.get("task_type") or ("checkout_cleaning" if departure else "room_status"),
                "status": task_status or ("pending" if room_status in {"dirty", "cleaning"} else "ready"),
                "assigned_to": task.get("assigned_to_name") or task.get("assigned_to"),
                "priority": task.get("priority") or ("high" if departure else "normal"),
                "created_at": task.get("created_at"),
                "started_at": task.get("started_at"),
                "completed_at": task.get("completed_at"),
                "due_out": bool(departure),
                "departed": departed,
                "departure_guest": _guest_display_name(guests_by_id.get(str((departure or {}).get("guest_id"))), departure or {}) if departure else None,
                "scheduled_checkout": (departure or {}).get("check_out"),
                "actual_checkout": (departure or {}).get("checked_out_at"),
            }
        )
    hk_completed = sum(1 for row in housekeeping_rows if row["status"] == "completed")
    hk_pending = sum(1 for row in housekeeping_rows if row["status"] in {"pending", "assigned", "open", "new"})
    hk_in_progress = sum(1 for row in housekeeping_rows if row["status"] in {"in_progress", "inprogress", "active", "cleaning"})

    source_distribution = {}
    source_revenue = {}
    source_revenue_by_currency: dict[str, dict[str, float]] = {}
    source_booking_ids: dict[str, set[str]] = {}
    for bk in recent_bookings:
        src = bk.get("booking_source", "direct")
        source_booking_ids.setdefault(src, set()).add(str(bk.get("id") or f"arrival:{len(source_booking_ids.get(src, set()))}"))
    booking_source_by_id = {
        str(booking.get("id")): booking.get("booking_source") or "direct"
        for booking in all_bk
        if booking.get("id")
    }
    for charge in charges_between(trend_start, today_start + timedelta(days=1)):
        src = booking_source_by_id.get(str(charge.get("booking_id")))
        if src:
            source_revenue[src] = source_revenue.get(src, 0) + charge_amount(charge)
            _add_currency_amount(source_revenue_by_currency.setdefault(src, {}), charge_currency(charge), charge_amount(charge))
            source_booking_ids.setdefault(src, set()).add(str(charge.get("booking_id")))
    source_distribution = {src: len(ids) for src, ids in source_booking_ids.items()}

    report_end = today_start + timedelta(days=1)
    week_charges = charges_between(week_start, report_end)
    month_charges = charges_between(trend_start, report_end)
    week_revenue = sum(charge_amount(charge) for charge in week_charges)
    month_revenue = sum(charge_amount(charge) for charge in month_charges)
    month_days = {str(row.get("date")) for row in metric_rows}

    def period_revenue_breakdown(charges: list[dict], days: set[str], revenue_source: str) -> dict[str, float]:
        non_room = _currency_breakdown(
            [charge for charge in charges if str(charge.get("charge_category") or charge.get("charge_type") or "").strip().lower() not in ROOM_CHARGE_CATEGORIES],
            charge_amount,
            charge_currency,
        )
        room = _merge_currency_breakdowns(*(
            (room_charges_by_day_currency if revenue_source == "posted" else accrued_room_by_day_currency).get(day, {})
            for day in days
        ))
        return _merge_currency_breakdowns(non_room, room)

    week_revenue_by_currency = _currency_breakdown(week_charges, charge_amount, charge_currency)
    month_revenue_by_currency = _currency_breakdown(month_charges, charge_amount, charge_currency)
    daily_room_nights = int(daily_performance.get("sold_room_nights") or 0)
    daily_capacity = int(daily_performance.get("available_room_nights") or 0)
    period_room_nights = int(period_performance.get("sold_room_nights") or 0)
    period_capacity = int(period_performance.get("available_room_nights") or 0)
    daily_performance["room_revenue_by_currency"] = today_room_revenue_by_currency
    daily_currency_room_nights = sold_room_nights_by_day_currency.get(target_day, {})
    daily_performance["adr_by_currency"] = {
        code: round(amount / daily_currency_room_nights.get(code, daily_room_nights), 2)
        for code, amount in today_room_revenue_by_currency.items()
        if daily_currency_room_nights.get(code, daily_room_nights)
    } if daily_room_nights else {}
    daily_performance["revpar_by_currency"] = {
        code: round(amount / daily_capacity, 2) for code, amount in today_room_revenue_by_currency.items()
    } if daily_capacity else {}
    daily_performance["room_revenue"] = _single_currency_amount(today_room_revenue_by_currency)
    daily_performance["adr"] = _single_currency_amount(daily_performance["adr_by_currency"])
    daily_performance["revpar"] = _single_currency_amount(daily_performance["revpar_by_currency"])
    period_room_revenue_by_currency = period_revenue_breakdown(
        [charge for charge in month_charges if str(charge.get("charge_category") or charge.get("charge_type") or "").strip().lower() in ROOM_CHARGE_CATEGORIES],
        month_days,
        period_performance["revenue_source"],
    )
    period_performance["room_revenue_by_currency"] = period_room_revenue_by_currency
    period_currency_room_nights = _merge_currency_breakdowns(*(
        sold_room_nights_by_day_currency.get(day, {}) for day in month_days
    ))
    period_performance["adr_by_currency"] = {
        code: round(amount / period_currency_room_nights.get(code, period_room_nights), 2)
        for code, amount in period_room_revenue_by_currency.items()
        if period_currency_room_nights.get(code, period_room_nights)
    } if period_room_nights else {}
    period_performance["revpar_by_currency"] = {
        code: round(amount / period_capacity, 2) for code, amount in period_room_revenue_by_currency.items()
    } if period_capacity else {}
    period_performance["room_revenue"] = _single_currency_amount(period_room_revenue_by_currency)
    period_performance["adr"] = _single_currency_amount(period_performance["adr_by_currency"])
    period_performance["revpar"] = _single_currency_amount(period_performance["revpar_by_currency"])

    # Milliyet dağılımı rezervasyon sayısını değil, rapor dönemindeki tüm
    # konaklayan kişileri (ek misafirler dahil) sayar.
    country_dist = {}
    for guest_row in recent_guests_data:
        c = _normalized_nationality(guest_row.get("nationality"))
        country_dist[c] = country_dist.get(c, 0) + 1

    blocked_room_ids = {
        str(block.get("room_id"))
        for block in room_blocks
        if block.get("room_id")
        and _date_part(block.get("start_date")) <= target_day
        and (not block.get("end_date") or target_day < _date_part(block.get("end_date")))
    }
    occupied_room_ids = {
        str(booking.get("room_id"))
        for booking in all_bk
        if booking.get("room_id") and _booking_occupied_on(booking, target_day)
    }
    room_type_occ = {}
    for rt_name in room_types:
        rt_rooms = [r for r in active_rooms if _normalized_room_type(r.get("room_type")) == rt_name and str(r.get("id")) not in blocked_room_ids]
        rt_room_ids = {str(r.get("id")) for r in rt_rooms if r.get("id")}
        rt_count = len(rt_rooms)
        rt_occ = len(rt_room_ids & occupied_room_ids)
        room_type_occ[rt_name] = {"total": rt_count, "occupied": rt_occ, "occupancy": round((rt_occ / rt_count * 100), 1) if rt_count > 0 else 0, "revenue": 0, "revenue_by_currency": {}}
    booking_room_types = {str(booking.get("id")): _normalized_room_type(booking.get("room_type")) for booking in all_bk if booking.get("id")}
    for charge in charges_between(trend_start, report_end):
        rt = booking_room_types.get(str(charge.get("booking_id")))
        if rt in room_type_occ:
            room_type_occ[rt]["revenue"] += charge_amount(charge)
            _add_currency_amount(room_type_occ[rt]["revenue_by_currency"], charge_currency(charge), charge_amount(charge))
    for rt in room_type_occ:
        room_type_occ[rt]["revenue_by_currency"] = {
            code: round(amount, 2) for code, amount in sorted(room_type_occ[rt]["revenue_by_currency"].items())
        }
        room_type_occ[rt]["revenue"] = _single_currency_amount(room_type_occ[rt]["revenue_by_currency"])

    booking_by_id = {
        str(booking.get("id")): booking
        for booking in [*all_bk, *payment_only_bookings]
        if booking.get("id")
    }
    payment_methods = {}
    total_paid = 0
    payment_totals_by_currency: dict[str, float] = {}
    received_payment_totals_by_currency: dict[str, float] = {}
    ledger_payment_totals_by_currency: dict[str, float] = {}
    payment_totals_by_method_currency: dict[str, dict[str, float]] = {}
    payment_conversion_issues = []
    payment_rows = []
    for p in all_payments:
        if not _payment_is_collection(p):
            continue
        method = _payment_method(p)
        amt = float(p.get("amount", 0) or 0)
        if str(p.get("payment_type") or "").lower() == "refund" and amt > 0:
            amt = -amt
        payment_booking = booking_by_id.get(str(p.get("booking_id"))) or {}
        received = _received_payment_amount(p, p.get("currency") or payment_booking.get("currency") or "TRY")
        received_currency = str(received.get("currency") or "TRY").upper()
        received_amount = float(received.get("amount") or 0)
        ledger_currency = str(p.get("currency") or payment_booking.get("currency") or "TRY").upper()
        ledger_payment_totals_by_currency[ledger_currency] = ledger_payment_totals_by_currency.get(ledger_currency, 0) + amt
        received_payment_totals_by_currency[received_currency] = received_payment_totals_by_currency.get(received_currency, 0) + received_amount
        reporting_amount = reporting_collection_amount(p)
        if reporting_amount is None:
            payment_conversion_issues.append({
                "id": p.get("id"),
                "currency": ledger_currency,
                "received_currency": received_currency,
                "reason": "historical_exchange_rate_missing",
            })
        else:
            total_paid += reporting_amount
            payment_totals_by_currency[REPORTING_CURRENCY] = payment_totals_by_currency.get(REPORTING_CURRENCY, 0) + reporting_amount
            method_totals = payment_totals_by_method_currency.setdefault(method, {})
            method_totals[REPORTING_CURRENCY] = method_totals.get(REPORTING_CURRENCY, 0) + reporting_amount
            payment_methods[method] = payment_methods.get(method, 0) + reporting_amount
        payment_rows.append(
            {
                "id": p.get("id"),
                "booking_id": p.get("booking_id"),
                "folio_id": p.get("folio_id"),
                "room_number": str(p.get("room_number") or payment_booking.get("room_number") or room_map.get(str(payment_booking.get("room_id"))) or "?").strip() or "?",
                "guest_name": _guest_display_name(guests_by_id.get(str(payment_booking.get("guest_id"))), payment_booking) if payment_booking else None,
                "amount": round(amt, 2),
                "currency": ledger_currency,
                "received_amount": round(received_amount, 2),
                "received_currency": received_currency,
                "reporting_amount": round(reporting_amount, 2) if reporting_amount is not None else None,
                "reporting_currency": REPORTING_CURRENCY,
                "conversion_missing": reporting_amount is None,
                "exchange_rate": p.get("exchange_rate"),
                "exchange_rate_date": p.get("exchange_rate_date") or p.get("payment_date") or str(p.get("processed_at") or "")[:10],
                "method": method,
                "payment_type": p.get("payment_type"),
                "status": p.get("status") or "paid",
                "reference": p.get("reference"),
                "notes": p.get("notes"),
                "processed_by": p.get("processed_by_name") or p.get("created_by_name") or p.get("processed_by") or p.get("created_by"),
                "processed_at": p.get("processed_at") or p.get("payment_date") or p.get("date") or p.get("created_at"),
            }
        )
    payment_methods = {method: round(amount, 2) for method, amount in payment_methods.items()}

    daily_charges = daily_period_charges
    charge_totals_by_currency = _currency_breakdown(daily_charges, charge_amount, charge_currency)
    balance_change_by_currency = {
        code: round(charge_totals_by_currency.get(code, 0) - ledger_payment_totals_by_currency.get(code, 0), 2)
        for code in set(charge_totals_by_currency) | set(ledger_payment_totals_by_currency)
    }
    uncollected_by_currency = {code: max(amount, 0) for code, amount in balance_change_by_currency.items()}
    charge_total = _single_currency_amount(charge_totals_by_currency)
    total_paid = round(total_paid, 2)
    cash_breakdown = payment_totals_by_method_currency.get("cash", {})
    cash_total = _single_currency_amount(cash_breakdown)
    non_cash_breakdown = _merge_currency_breakdowns(*(
        totals for method, totals in payment_totals_by_method_currency.items() if method != "cash"
    ))
    non_cash_total = _single_currency_amount(non_cash_breakdown)
    daily_balance_change = _single_currency_amount(balance_change_by_currency)
    uncollected_charges = _single_currency_amount(uncollected_by_currency)

    room_rate_rows = []
    occupied_booking_ids = {row.get("booking_id") for row in daily_in_house if row.get("booking_id")}
    for booking in all_bk:
        if booking.get("id") not in occupied_booking_ids:
            continue
        booking_id = str(booking.get("id"))
        daily_rate = daily_rates_by_booking.get(booking_id)
        agreed_rate = _nightly_booking_rate(booking, target_day, daily_rate)
        comp_info = _complimentary_night_info(
            booking,
            target_day,
            daily_rate,
            payments_by_booking.get(booking_id),
        )
        room = next((r for r in rooms if str(r.get("id")) == str(booking.get("room_id"))), {})
        posted_rate = round(
            sum(
                charge_amount(charge)
                for charge in daily_charges
                if str(charge.get("booking_id")) == str(booking.get("id"))
                and str(charge.get("charge_category") or charge.get("charge_type") or "").lower() in {"room", "accommodation", "room_charge"}
            ),
            2,
        )
        room_rate_rows.append(
            {
                "booking_id": booking.get("id"),
                "room_number": str(booking.get("room_number") or room_map.get(str(booking.get("room_id"))) or "?").strip() or "?",
                "room_type": booking.get("room_type") or room.get("room_type"),
                "guest_name": _guest_display_name(guests_by_id.get(str(booking.get("guest_id"))), booking),
                "agreed_rate": agreed_rate,
                "posted_rate": posted_rate,
                "variance": round(posted_rate - agreed_rate, 2),
                "currency": str(booking.get("currency") or "TRY").upper(),
                "posting_status": "complimentary" if comp_info["is_complimentary_night"] else ("posted" if posted_rate else "pending"),
                **comp_info,
            }
        )

    expected_room_revenue = round(sum(row["agreed_rate"] for row in room_rate_rows), 2)
    analysis_room_revenue = daily_performance["room_revenue"]
    analysis_revenue_source = daily_performance["revenue_source"]
    analysis_adr = daily_performance["adr"]
    analysis_revpar = daily_performance["revpar"]

    previous_charges = charges_between(previous_start, previous_end)
    prev_metrics = await load_stay_night_metrics(
        db,
        tenant_id,
        previous_start.date(),
        (previous_end - timedelta(days=1)).date(),
        actual_only=True,
    )
    prev_room_charges_by_day: dict[str, float] = {}
    for charge in charges_between(previous_start, previous_end):
        category = str(charge.get("charge_category") or charge.get("charge_type") or "").lower()
        if category in ROOM_CHARGE_CATEGORIES:
            day = _date_part(charge.get("business_date") or charge.get("date"))
            prev_room_charges_by_day[day] = prev_room_charges_by_day.get(day, 0.0) + charge_amount(charge)
    prev_performance = _period_performance(prev_metrics, prev_room_charges_by_day)
    prev_revenue = sum(charge_amount(charge) for charge in previous_charges)
    prev_revenue_by_currency = _currency_breakdown(previous_charges, charge_amount, charge_currency)
    prev_adr = prev_performance["adr"]
    ly_charges = charges_between(last_year_start, last_year_end)
    ly_revenue = sum(charge_amount(charge) for charge in ly_charges)
    ly_revenue_by_currency = _currency_breakdown(ly_charges, charge_amount, charge_currency)

    today_revenue = _single_currency_amount(today_revenue_by_currency)
    week_revenue = _single_currency_amount(week_revenue_by_currency)
    month_revenue = _single_currency_amount(month_revenue_by_currency)
    prev_revenue = _single_currency_amount(prev_revenue_by_currency)
    ly_revenue = _single_currency_amount(ly_revenue_by_currency)

    return {
        "date": today.strftime("%Y-%m-%d"),
        "summary": {
            "total_rooms": available_rooms_today,
            "physical_rooms": total_rooms,
            "blocked_rooms": max(total_rooms - available_rooms_today, 0),
            "occupied_rooms": occupied_today,
            "occupancy_percentage": occupancy_pct,
            "arrivals": arrivals,
            "departures": departures,
            "in_house": in_house,
            "no_shows": no_shows,
            "cancellations": cancellations,
            "today_revenue": round(today_revenue, 2),
            "today_revenue_by_currency": today_revenue_by_currency,
            "today_revenue_source": "posted",
            "today_room_revenue": daily_performance["room_revenue"],
            "today_room_revenue_by_currency": today_room_revenue_by_currency,
            "posted_room_revenue": today_room_revenue,
            "room_revenue_source": daily_performance["revenue_source"],
            "adr": adr,
            "adr_by_currency": daily_performance["adr_by_currency"],
            "revpar": revpar,
            "revpar_by_currency": daily_performance["revpar_by_currency"],
            "fnb_revenue": round(fnb_revenue, 2),
            "fnb_revenue_by_currency": fnb_revenue_by_currency,
        },
        "period_metrics": period_performance,
        "period_activity": {
            "arrivals": period_arrivals,
            "departures": period_departures,
            "no_shows": period_no_shows,
            "cancellations": period_cancellations,
        },
        "period_comparison": {
            "week_revenue": round(week_revenue, 2),
            "week_revenue_by_currency": week_revenue_by_currency,
            "week_revenue_source": "posted",
            "week_bookings": len(week_bookings),
            "month_revenue": round(month_revenue, 2),
            "month_revenue_by_currency": month_revenue_by_currency,
            "month_revenue_source": "posted",
            "month_bookings": len(month_bookings),
            "prev_month_revenue": round(prev_revenue, 2),
            "prev_month_revenue_by_currency": prev_revenue_by_currency,
            "prev_month_bookings": len(prev_bookings),
            "prev_month_adr": prev_adr,
            "prev_period_occupancy": prev_performance["occupancy_percentage"],
            "prev_period_revpar": prev_performance["revpar"],
            "last_year_revenue": round(ly_revenue, 2),
            "last_year_revenue_by_currency": ly_revenue_by_currency,
            "last_year_bookings": len(ly_bookings),
        },
        "occupancy_trend": occupancy_trend,
        "revenue_trend": revenue_trend,
        "room_status": room_status_counts,
        "room_status_snapshot": "current",
        "room_types": room_types,
        "room_type_occupancy": room_type_occ,
        "booking_sources": {
            "distribution": source_distribution,
            "revenue": {
                source: _single_currency_amount(totals)
                for source, totals in source_revenue_by_currency.items()
            },
            "revenue_by_currency": {
                source: {code: round(amount, 2) for code, amount in sorted(totals.items())}
                for source, totals in source_revenue_by_currency.items()
            },
        },
        "country_distribution": country_dist,
        "payments": {
            "by_method": payment_methods,
            "total_paid": round(total_paid, 2),
            "total_pending": pending_invoices,
            "transaction_count": len(payment_rows),
            "rows": sorted(payment_rows, key=lambda row: str(row.get("processed_at") or "")),
            "totals_by_currency": {code: round(amount, 2) for code, amount in payment_totals_by_currency.items()},
            "reporting_currency": REPORTING_CURRENCY,
            "received_totals_by_currency": {code: round(amount, 2) for code, amount in received_payment_totals_by_currency.items()},
            "conversion_issue_count": len(payment_conversion_issues),
            "conversion_issues": payment_conversion_issues,
            "totals_by_method_currency": {
                method: {code: round(amount, 2) for code, amount in totals.items()}
                for method, totals in payment_totals_by_method_currency.items()
            },
            "currency_exchanges": currency_exchanges,
        },
        # P1 fix: Polis bildirimi ve maliye listesinde 100 kayıt yetersiz —
        # tüm aylık misafir listesi (cap 5000) döndürülür; frontend tarafı
        # sayfalar / arama ile sınırlı gösterim yapar.
        "guest_list": recent_guests_data[:5000],
        "daily_lists": {
            "in_house": daily_in_house,
            "arrivals": daily_arrivals,
            "departures": daily_departures,
        },
        "housekeeping": {
            "room_status_snapshot": "current",
            "completed": hk_completed,
            "pending": hk_pending,
            "in_progress": hk_in_progress,
            "total": len(housekeeping_rows),
            "dirty": sum(1 for row in housekeeping_rows if row["room_status"] == "dirty"),
            "clean": sum(1 for row in housekeeping_rows if row["room_status"] in {"available", "clean", "inspected"}),
            "due_out": sum(1 for row in housekeeping_rows if row["due_out"] and not row["departed"]),
            "departed": sum(1 for row in housekeeping_rows if row["departed"]),
            "rows": sorted(housekeeping_rows, key=lambda row: (str(row.get("room_number") or ""), str(row.get("created_at") or ""))),
        },
        "front_cashier": {
            "charge_total": charge_total,
            "charge_total_by_currency": charge_totals_by_currency,
            "collection_total": total_paid,
            "cash_total": cash_total,
            "non_cash_total": non_cash_total,
            "net_cash_movement": cash_total,
            "net_cash_movement_by_currency": payment_totals_by_method_currency.get("cash", {}),
            "daily_balance_change": daily_balance_change,
            "daily_balance_change_by_currency": balance_change_by_currency,
            "uncollected_charges": uncollected_charges,
            "uncollected_charges_by_currency": uncollected_by_currency,
            "charge_count": len(daily_charges),
            "payment_count": len(payment_rows),
        },
        "room_rate_control": room_rate_rows,
        "daily_analysis": {
            "date": target_day,
            "occupied_rooms": occupied_today,
            "total_rooms": available_rooms_today,
            "physical_rooms": total_rooms,
            "blocked_rooms": max(total_rooms - available_rooms_today, 0),
            "occupancy_percentage": occupancy_pct,
            "arrivals": arrivals,
            "departures": departures,
            "in_house_guests": len(daily_in_house),
            "room_revenue": analysis_room_revenue,
            "room_revenue_by_currency": daily_performance["room_revenue_by_currency"],
            "posted_room_revenue": today_room_revenue,
            "posted_room_revenue_by_currency": posted_room_revenue_by_currency,
            "expected_room_revenue": expected_room_revenue,
            "revenue_source": analysis_revenue_source,
            "adr": analysis_adr,
            "revpar": analysis_revpar,
            "collections": total_paid,
            "collections_by_currency": {code: round(amount, 2) for code, amount in payment_totals_by_currency.items()},
            "adr_by_currency": daily_performance["adr_by_currency"],
            "revpar_by_currency": daily_performance["revpar_by_currency"],
        },
        "maintenance": {"open": maint_open, "completed_month": maint_completed},
        "finance": {"pending_invoices": pending_invoices, "paid_invoices_month": paid_invoices},
    }
