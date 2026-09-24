"""Auto-split from reports.py — backward-compatible sub-router."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from core.business_date_service import accounting_day_match
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
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

    actual_in = _date_part(booking.get("checked_in_at"))
    actual_out = _date_part(booking.get("checked_out_at"))
    if actual_in and target_date < actual_in:
        return False
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
        "available_room_nights": available_room_nights,
        "occupancy_percentage": round(occupied_room_nights / available_room_nights * 100, 2) if available_room_nights else 0,
        "posted_room_revenue": posted_room_revenue,
        "accrued_room_revenue": accrued_room_revenue,
        "room_revenue": round(room_revenue, 2),
        "revenue_source": "posted" if use_posted else "accrued",
        "posting_gap_days": posting_gap_days,
        "adr": round(room_revenue / occupied_room_nights, 2) if occupied_room_nights else 0,
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

    Verilen tarihte (veya bugün) otelde konaklayan tüm misafirleri ve konaklama
    bilgilerini döner. Check-in <= tarih <= Check-out koşulunu kullanır.
    """
    target_date = datetime.now(UTC).date() if not date else datetime.fromisoformat(date).date()
    has_pii = _user_has_pii_access(current_user)

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
                {
                    "id": f"{b.get('id')}:{guest_id or occupant_index}",
                    "booking_id": b.get("id"),
                    "guest_id": guest_id,
                    "guest_name": _guest_display_name(guest, b if occupant_index == 0 else {}),
                    "national_id": national_id if has_pii else _mask_pii(national_id),
                    "passport_number": passport_number if has_pii else _mask_pii(passport_number),
                    "country": (guest or {}).get("country") or (guest or {}).get("nationality"),
                    "city": (guest or {}).get("city"),
                    "date_of_birth": (
                        (guest or {}).get("date_of_birth") or (guest or {}).get("birth_date")
                        if has_pii
                        else _mask_pii((guest or {}).get("date_of_birth") or (guest or {}).get("birth_date"))
                    ),
                    "room_number": str(b.get("room_number") or room_map.get(str(b.get("room_id"))) or "?").strip() or "?",
                    "check_in": b.get("check_in"),
                    "check_out": b.get("check_out"),
                    "adults": b.get("adults", 1) if occupant_index == 0 else 0,
                    "children": b.get("children", 0) if occupant_index == 0 else 0,
                    "reservation_adults": b.get("adults", 1),
                    "reservation_children": b.get("children", 0),
                    "total_amount": b.get("total_amount", 0.0) if occupant_index == 0 else 0.0,
                    "billing_tax_number": b.get("billing_tax_number") if has_pii else _mask_pii(b.get("billing_tax_number")),
                    "billing_address": b.get("billing_address") if has_pii else _mask_pii(b.get("billing_address")),
                    "company_id": b.get("company_id") if has_pii else _mask_pii(b.get("company_id")),
                    "market_segment": b.get("market_segment"),
                }
            )

    return {
        "date": target_date.isoformat(),
        "count": len(rows),
        "rows": rows,
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
    has_pii = _user_has_pii_access(current_user)
    return await _basic_dashboard_impl(current_user, has_pii, date, period)


@cached(ttl=120, key_prefix="reports_basic_dashboard_v2", role_aware=True)
async def _basic_dashboard_impl(current_user: User, has_pii: bool, target_date: str = None, period: str = "monthly"):
    if target_date:
        try:
            today = datetime.fromisoformat(target_date[:10]).replace(tzinfo=UTC)
        except ValueError:
            today = datetime.now(UTC)
    else:
        today = datetime.now(UTC)
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
        try:
            return await db.pos_orders.find(
                {
                    "tenant_id": tenant_id,
                    "status": {"$nin": ["cancelled", "canceled", "void", "voided"]},
                    "$or": [
                        {"business_date": {"$gte": charge_range_start, "$lte": target_day}},
                        {"closed_at": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                        {"created_at": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                    ],
                },
                {
                    "_id": 0,
                    "id": 1,
                    "business_date": 1,
                    "closed_at": 1,
                    "created_at": 1,
                    "total_amount": 1,
                    "grand_total": 1,
                    "status": 1,
                    "payment_status": 1,
                },
            ).to_list(5000)
        except Exception:
            return []

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
                "check_in": {"$gte": previous_start.date().isoformat(), "$lt": previous_end.date().isoformat()},
                "status": {"$in": ["confirmed", "checked_in", "checked_out"]},
            },
            {"_id": 0, "total_amount": 1, "check_in": 1, "check_out": 1},
        ).to_list(10000),
        db.bookings.find(
            {
                "tenant_id": tenant_id,
                "check_in": {"$gte": last_year_start.date().isoformat(), "$lt": last_year_end.date().isoformat()},
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
            {"_id": 0, "booking_id": 1, "date": 1, "rate": 1},
        ).to_list(10000)
        if booking_ids
        else []
    )
    daily_rates_by_booking = {str(row.get("booking_id")): row for row in daily_rate_rows}

    period_charges = await db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"business_date": {"$gte": charge_range_start, "$lte": target_day}},
                {"business_date": {"$exists": False}, "date": {"$gte": charge_range_start, "$lt": next_day.date().isoformat()}},
                {"business_date": None, "date": {"$gte": charge_range_start, "$lt": next_day.date().isoformat()}},
                {"business_date": {"$exists": False}, "date": {"$gte": charge_range_start_dt, "$lt": next_day}},
                {"business_date": None, "date": {"$gte": charge_range_start_dt, "$lt": next_day}},
                {"business_date": {"$exists": False}, "date": {"$exists": False}, "created_at": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                {"business_date": {"$exists": False}, "date": {"$exists": False}, "created_at": {"$gte": charge_range_start_dt, "$lt": next_day}},
            ],
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
            "$or": [
                {"business_date": {"$gte": charge_range_start, "$lte": target_day}},
                {"charge_date": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                {"charge_date": {"$gte": charge_range_start_dt, "$lt": next_day}},
                {"date": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                {"date": {"$gte": charge_range_start_dt, "$lt": next_day}},
                {"created_at": {"$gte": charge_range_start, "$lt": next_day.isoformat()}},
                {"created_at": {"$gte": charge_range_start_dt, "$lt": next_day}},
            ],
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
            "_source": "direct_pos",
        }
        for order in fnb_orders
        if str(order.get("id") or "") not in represented_pos_order_ids
        and str(order.get("status") or "").lower() in {"closed", "completed", "served", "paid"}
    )

    def charge_amount(charge: dict) -> float:
        return float(charge.get("total") or charge.get("amount") or 0)

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
        rt = r.get("room_type", "Standard")
        room_types[rt] = room_types.get(rt, 0) + 1

    room_status_counts = {"available": 0, "occupied": 0, "dirty": 0, "maintenance": 0, "out_of_order": 0}
    for r in active_rooms:
        st = r.get("current_status", r.get("status", "available"))
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
    for charge in period_charges:
        charge_day = _date_part(charge.get("business_date") or charge.get("date"))
        amount = charge_amount(charge)
        charges_by_day[charge_day] = charges_by_day.get(charge_day, 0.0) + amount
        category = str(charge.get("charge_category") or charge.get("charge_type") or "").lower()
        if category in {"room", "accommodation", "room_charge"}:
            room_charges_by_day[charge_day] = room_charges_by_day.get(charge_day, 0.0) + amount
    today_room_revenue = round(room_charges_by_day.get(target_day, 0.0), 2)
    daily_period_charges = charges_between(today_start, next_day)
    fnb_revenue = round(sum(
        charge_amount(charge)
        for charge in daily_period_charges
        if str(charge.get("charge_category") or charge.get("charge_type") or "").strip().lower() in FNB_CHARGE_CATEGORIES
    ), 2)
    daily_performance = _period_performance([today_metric] if today_metric else [], room_charges_by_day)
    period_performance = _period_performance(metric_rows, room_charges_by_day)
    daily_non_room_revenue = sum(
        charge_amount(charge)
        for charge in daily_period_charges
        if str(charge.get("charge_category") or charge.get("charge_type") or "").strip().lower() not in ROOM_CHARGE_CATEGORIES
    )
    today_revenue = round(daily_non_room_revenue + daily_performance["room_revenue"], 2)
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
        posted_total = charges_by_day.get(day, 0.0)
        posted_room = room_charges_by_day.get(day, 0.0)
        effective_room = posted_room if posted_room else float(row.get("revenue") or 0)
        revenue_trend.append(
            {
                "date": day,
                "label": datetime.fromisoformat(day).strftime("%d %b"),
                "revenue": round(posted_total - posted_room + effective_room, 2),
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
        room_status = str(room.get("housekeeping_status") or room.get("hk_status") or room.get("status") or "available").lower()
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
            source_booking_ids.setdefault(src, set()).add(str(charge.get("booking_id")))
    source_distribution = {src: len(ids) for src, ids in source_booking_ids.items()}

    report_end = today_start + timedelta(days=1)
    week_charges = charges_between(week_start, report_end)
    month_charges = charges_between(trend_start, report_end)
    week_metrics = [row for row in metric_rows if row["date"] >= week_start.date().isoformat()]
    week_performance = _period_performance(week_metrics, room_charges_by_day)
    week_non_room_revenue = sum(
        charge_amount(charge)
        for charge in week_charges
        if str(charge.get("charge_category") or charge.get("charge_type") or "").strip().lower() not in ROOM_CHARGE_CATEGORIES
    )
    month_non_room_revenue = sum(
        charge_amount(charge)
        for charge in month_charges
        if str(charge.get("charge_category") or charge.get("charge_type") or "").strip().lower() not in ROOM_CHARGE_CATEGORIES
    )
    week_revenue = week_non_room_revenue + week_performance["room_revenue"]
    month_revenue = month_non_room_revenue + period_performance["room_revenue"]

    # Milliyet dağılımı rezervasyon sayısını değil, rapor dönemindeki tüm
    # konaklayan kişileri (ek misafirler dahil) sayar.
    country_dist = {}
    for guest_row in recent_guests_data:
        c = guest_row.get("nationality") or "Belirtilmemiş"
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
        rt_rooms = [r for r in active_rooms if r.get("room_type", "Standard") == rt_name and str(r.get("id")) not in blocked_room_ids]
        rt_room_ids = {str(r.get("id")) for r in rt_rooms if r.get("id")}
        rt_count = len(rt_rooms)
        rt_occ = len(rt_room_ids & occupied_room_ids)
        room_type_occ[rt_name] = {"total": rt_count, "occupied": rt_occ, "occupancy": round((rt_occ / rt_count * 100), 1) if rt_count > 0 else 0, "revenue": 0}
    booking_room_types = {str(booking.get("id")): booking.get("room_type", "Standard") for booking in all_bk if booking.get("id")}
    for charge in charges_between(trend_start, report_end):
        rt = booking_room_types.get(str(charge.get("booking_id")))
        if rt in room_type_occ:
            room_type_occ[rt]["revenue"] += charge_amount(charge)
    for rt in room_type_occ:
        room_type_occ[rt]["revenue"] = round(room_type_occ[rt]["revenue"], 2)

    booking_by_id = {
        str(booking.get("id")): booking
        for booking in [*all_bk, *payment_only_bookings]
        if booking.get("id")
    }
    payment_methods = {}
    total_paid = 0
    payment_rows = []
    for p in all_payments:
        if not _payment_is_collection(p):
            continue
        method = _payment_method(p)
        amt = float(p.get("amount", 0) or 0)
        if str(p.get("payment_type") or "").lower() == "refund" and amt > 0:
            amt = -amt
        payment_methods[method] = payment_methods.get(method, 0) + amt
        total_paid += amt
        payment_booking = booking_by_id.get(str(p.get("booking_id"))) or {}
        payment_rows.append(
            {
                "id": p.get("id"),
                "booking_id": p.get("booking_id"),
                "folio_id": p.get("folio_id"),
                "room_number": str(p.get("room_number") or payment_booking.get("room_number") or room_map.get(str(payment_booking.get("room_id"))) or "?").strip() or "?",
                "guest_name": _guest_display_name(guests_by_id.get(str(payment_booking.get("guest_id"))), payment_booking) if payment_booking else None,
                "amount": round(amt, 2),
                "method": method,
                "payment_type": p.get("payment_type"),
                "status": p.get("status") or "paid",
                "reference": p.get("reference"),
                "notes": p.get("notes"),
                "processed_by": p.get("processed_by_name") or p.get("created_by_name") or p.get("processed_by") or p.get("created_by"),
                "processed_at": p.get("processed_at") or p.get("payment_date") or p.get("date") or p.get("created_at"),
            }
        )
    payment_methods = {k: round(v, 2) for k, v in payment_methods.items()}

    daily_charges = daily_period_charges
    charge_total = round(sum(float(c.get("total") or c.get("amount") or 0) for c in daily_charges), 2)
    cash_total = round(payment_methods.get("cash", 0), 2)

    room_rate_rows = []
    occupied_booking_ids = {row.get("booking_id") for row in daily_in_house if row.get("booking_id")}
    for booking in all_bk:
        if booking.get("id") not in occupied_booking_ids:
            continue
        agreed_rate = _nightly_booking_rate(booking, target_day, daily_rates_by_booking.get(str(booking.get("id"))))
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
                "posting_status": "posted" if posted_rate else "pending",
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
    prev_non_room_revenue = sum(
        charge_amount(charge)
        for charge in previous_charges
        if str(charge.get("charge_category") or charge.get("charge_type") or "").strip().lower() not in ROOM_CHARGE_CATEGORIES
    )
    prev_revenue = prev_non_room_revenue + prev_performance["room_revenue"]
    prev_adr = prev_performance["adr"]
    ly_revenue = sum(charge_amount(charge) for charge in charges_between(last_year_start, last_year_end))

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
            "today_room_revenue": daily_performance["room_revenue"],
            "posted_room_revenue": today_room_revenue,
            "room_revenue_source": daily_performance["revenue_source"],
            "adr": adr,
            "revpar": revpar,
            "fnb_revenue": round(fnb_revenue, 2),
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
            "week_bookings": len(week_bookings),
            "month_revenue": round(month_revenue, 2),
            "month_bookings": len(month_bookings),
            "prev_month_revenue": round(prev_revenue, 2),
            "prev_month_bookings": len(prev_bookings),
            "prev_month_adr": prev_adr,
            "prev_period_occupancy": prev_performance["occupancy_percentage"],
            "prev_period_revpar": prev_performance["revpar"],
            "last_year_revenue": round(ly_revenue, 2),
            "last_year_bookings": len(ly_bookings),
        },
        "occupancy_trend": occupancy_trend,
        "revenue_trend": revenue_trend,
        "room_status": room_status_counts,
        "room_types": room_types,
        "room_type_occupancy": room_type_occ,
        "booking_sources": {"distribution": source_distribution, "revenue": {k: round(v, 2) for k, v in source_revenue.items()}},
        "country_distribution": country_dist,
        "payments": {
            "by_method": payment_methods,
            "total_paid": round(total_paid, 2),
            "total_pending": pending_invoices,
            "transaction_count": len(payment_rows),
            "rows": sorted(payment_rows, key=lambda row: str(row.get("processed_at") or "")),
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
            "collection_total": round(total_paid, 2),
            "cash_total": cash_total,
            "non_cash_total": round(total_paid - cash_total, 2),
            "net_cash_movement": cash_total,
            "uncollected_charges": round(charge_total - total_paid, 2),
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
            "posted_room_revenue": today_room_revenue,
            "expected_room_revenue": expected_room_revenue,
            "revenue_source": analysis_revenue_source,
            "adr": analysis_adr,
            "revpar": analysis_revpar,
            "collections": round(total_paid, 2),
        },
        "maintenance": {"open": maint_open, "completed_month": maint_completed},
        "finance": {"pending_invoices": pending_invoices, "paid_invoices_month": paid_invoices},
    }
