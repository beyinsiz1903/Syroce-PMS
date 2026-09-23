"""Auto-split from reports.py — backward-compatible sub-router."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
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
IN_HOUSE_STATUSES = {"checked_in", "checked_out"}
ARRIVAL_STATUSES = {"confirmed", "guaranteed", "checked_in", "checked_out"}


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


def _guest_link_active_on(link: dict, target_date: str) -> bool:
    checkout_date = _date_part(link.get("checkout_date"))
    return not checkout_date or checkout_date > target_date


@sub_router.get("/reports/official-guest-list")
async def get_official_guest_list(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
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
    bookings_cursor = db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "check_in": {"$lt": next_day.date().isoformat()},
            "check_out": {"$gt": day_start.date().isoformat()},
            "status": {"$nin": ["cancelled", "no_show"]},
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
        for booking in await bookings_cursor.to_list(5000)
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
    ).to_list(10000) if booking_ids else []

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

        guest_docs = [decrypt_guest_doc(g) for g in await guests_cursor.to_list(5000)]
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
                    "date_of_birth": (guest or {}).get("date_of_birth") or (guest or {}).get("birth_date"),
                    "room_number": str(b.get("room_number") or room_map.get(str(b.get("room_id"))) or "?").strip() or "?",
                    "check_in": b.get("check_in"),
                    "check_out": b.get("check_out"),
                    "adults": b.get("adults", 1) if occupant_index == 0 else 0,
                    "children": b.get("children", 0) if occupant_index == 0 else 0,
                    "reservation_adults": b.get("adults", 1),
                    "reservation_children": b.get("children", 0),
                    "total_amount": b.get("total_amount", 0.0) if occupant_index == 0 else 0.0,
                    "billing_tax_number": b.get("billing_tax_number"),
                    "billing_address": b.get("billing_address"),
                    "company_id": b.get("company_id"),
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


@cached(ttl=120, key_prefix="reports:basic_dashboard", role_aware=True)
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


    # ALL queries in parallel
    async def get_fnb():
        try:
            orders = await db.pos_orders.find({"tenant_id": tenant_id, "created_at": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()}}, {"_id": 0, "total_amount": 1}).to_list(1000)
            return sum(o.get("total_amount", 0) for o in orders)
        except Exception:
            return 0.0

    results = await asyncio.gather(
        db.rooms.find({"tenant_id": tenant_id}).to_list(1000),
        db.bookings.find(
            {
                "tenant_id": tenant_id,
                "$or": [
                    {"check_in": {"$gte": trend_start.date().isoformat(), "$lt": next_day.date().isoformat()}},
                    {"check_out": {"$gte": trend_start.date().isoformat(), "$lt": next_day.date().isoformat()}},
                    {"check_in": {"$lt": trend_start.date().isoformat()}, "check_out": {"$gt": target_day}},
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
                "$or": [
                    {"processed_at": {"$regex": f"^{target_day}"}},
                    {"payment_date": target_day},
                    {"date": target_day},
                    {"created_at": {"$regex": f"^{target_day}"}},
                    {"created_at": {"$gte": today_start.isoformat(), "$lt": next_day.isoformat()}},
                ],
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
        get_fnb(),
    )
    rooms, all_bk, in_house, hk_tasks, maint_open, maint_completed, pending_invoices, paid_invoices, all_guests, all_payments, prev_bookings, ly_bookings, room_blocks, fnb_revenue = results

    charge_range_start = min(last_year_start, previous_start, trend_start).date().isoformat()
    period_charges = await db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"business_date": {"$gte": charge_range_start, "$lte": target_day}},
                {"business_date": {"$exists": False}, "date": {"$gte": charge_range_start, "$lt": next_day.date().isoformat()}},
                {"business_date": None, "date": {"$gte": charge_range_start, "$lt": next_day.date().isoformat()}},
            ],
        },
        {"_id": 0, "business_date": 1, "date": 1, "total": 1, "amount": 1, "charge_category": 1, "charge_type": 1, "booking_id": 1},
    ).to_list(50000)

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
    for r in rooms:
        rt = r.get("room_type", "Standard")
        room_types[rt] = room_types.get(rt, 0) + 1

    room_status_counts = {"available": 0, "occupied": 0, "dirty": 0, "maintenance": 0, "out_of_order": 0}
    for r in rooms:
        st = r.get("current_status", r.get("status", "available"))
        room_status_counts[st] = room_status_counts.get(st, room_status_counts.get("available", 0)) + 1

    ts_s, ts_e = today_start.isoformat(), today_end.isoformat()
    ms_s = month_start.isoformat()
    month_day, week_day = month_start.date().isoformat(), week_start.date().isoformat()
    occupied_today = arrivals = departures = no_shows = cancellations = today_revenue = 0
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
        created = bk.get("created_at", "")
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
        if status == "cancelled" and created >= ts_s and created <= ts_e:
            cancellations += 1
        if created >= ms_s:
            recent_bookings.append(bk)
        if ci_day >= week_day and status in ALL_REVENUE_STATUSES:
            week_bookings.append(bk)
        # P1 fix: ay listesi — cancelled / no_show da dahil edilmeli; aksi
        # halde "No-Show & İptaller" sekmesi recent_guests_data filtresinden
        # geçemediği için boş görünür.
        if ci_day >= month_day and status in (*ALL_REVENUE_STATUSES, "cancelled", "no_show"):
            if status in ALL_REVENUE_STATUSES:
                month_bookings.append(bk)
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
    today_revenue = round(charges_by_day.get(target_day, 0.0), 2)
    today_room_revenue = round(room_charges_by_day.get(target_day, 0.0), 2)
    occupancy_pct = today_metric.get("occupancy_rate", 0)
    adr = round(today_room_revenue / occupied_today, 2) if occupied_today else 0
    available_rooms_today = int(today_metric.get("total_rooms", total_rooms) or 0)
    revpar = round(today_room_revenue / available_rooms_today, 2) if available_rooms_today else 0
    occupancy_trend = [
        {"date": row["date"], "label": datetime.fromisoformat(row["date"]).strftime("%d %b"), "occupancy": row["occupancy_rate"], "rooms_occupied": row["occupied_rooms"]} for row in metric_rows
    ]
    revenue_trend = [
        {"date": row["date"], "label": datetime.fromisoformat(row["date"]).strftime("%d %b"), "revenue": round(charges_by_day.get(row["date"], 0.0), 2)}
        for row in metric_rows
    ]

    hk_completed = len([t for t in hk_tasks if str(t.get("status") or t.get("task_status") or "").strip().lower() == "completed"])
    hk_pending = len([t for t in hk_tasks if str(t.get("status") or t.get("task_status") or "").strip().lower() in ["pending", "assigned", "open"]])
    hk_in_progress = len([t for t in hk_tasks if str(t.get("status") or t.get("task_status") or "").strip().lower() in ["in_progress", "inprogress", "active"]])
    housekeeping_rows = [
        {
            "id": task.get("id"),
            "room_number": str(task.get("room_number") or room_map.get(str(task.get("room_id"))) or "?").strip() or "?",
            "task_type": task.get("task_type") or "cleaning",
            "status": task.get("status") or task.get("task_status") or "pending",
            "assigned_to": task.get("assigned_to") or task.get("assigned_to_name"),
            "priority": task.get("priority") or "normal",
            "created_at": task.get("created_at"),
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at"),
        }
        for task in hk_tasks
    ]

    source_distribution = {}
    source_revenue = {}
    for bk in recent_bookings:
        src = bk.get("booking_source", "direct")
        source_distribution[src] = source_distribution.get(src, 0) + 1
        source_revenue[src] = source_revenue.get(src, 0) + (bk.get("total_amount", 0) or 0)

    report_end = today_start + timedelta(days=1)
    week_revenue = sum(charge_amount(charge) for charge in charges_between(week_start, report_end))
    month_revenue = sum(charge_amount(charge) for charge in charges_between(trend_start, report_end))

    # P1 fix: Milliyet dağılımı tüm zamanlar yerine SADECE bu ayın
    # rezervasyonlarından (month_bookings) türetilir. Booking üstünde
    # nationality yoksa guest dokümanından lookup yapılır.
    guests_by_id = {g.get("id"): g for g in all_guests if g.get("id")}
    country_dist = {}
    for bk in month_bookings:
        c = bk.get("nationality")
        if not c:
            g = guests_by_id.get(bk.get("guest_id"))
            if g:
                c = g.get("nationality") or g.get("country")
        c = c or "Belirtilmemiş"
        country_dist[c] = country_dist.get(c, 0) + 1

    room_type_occ = {}
    for rt_name, rt_count in room_types.items():
        rt_rooms = [r for r in rooms if r.get("room_type") == rt_name]
        rt_occ = len([r for r in rt_rooms if r.get("current_status") == "occupied"])
        room_type_occ[rt_name] = {"total": rt_count, "occupied": rt_occ, "occupancy": round((rt_occ / rt_count * 100), 1) if rt_count > 0 else 0, "revenue": 0}
    booking_room_types = {str(booking.get("id")): booking.get("room_type", "Standard") for booking in all_bk if booking.get("id")}
    for charge in charges_between(trend_start, report_end):
        rt = booking_room_types.get(str(charge.get("booking_id")))
        if rt in room_type_occ:
            room_type_occ[rt]["revenue"] += charge_amount(charge)
    for rt in room_type_occ:
        room_type_occ[rt]["revenue"] = round(room_type_occ[rt]["revenue"], 2)

    payment_methods = {}
    total_paid = 0
    payment_rows = []
    for p in all_payments:
        if not _payment_is_effective(p):
            continue
        method = _payment_method(p)
        amt = float(p.get("amount", 0) or 0)
        if str(p.get("payment_type") or "").lower() == "refund" and amt > 0:
            amt = -amt
        payment_methods[method] = payment_methods.get(method, 0) + amt
        if method not in NON_CASH_PAYMENT_METHODS:
            total_paid += amt
        payment_rows.append(
            {
                "id": p.get("id"),
                "booking_id": p.get("booking_id"),
                "folio_id": p.get("folio_id"),
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

    daily_charges = await db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"business_date": target_day},
                {"date": target_day},
                {"date": {"$regex": f"^{target_day}"}},
                {"date": {"$gte": today_start.isoformat(), "$lt": next_day.isoformat()}},
                {"posted_at": {"$regex": f"^{target_day}"}},
                {"posted_at": {"$gte": today_start.isoformat(), "$lt": next_day.isoformat()}},
                {"created_at": {"$regex": f"^{target_day}"}},
                {"created_at": {"$gte": today_start.isoformat(), "$lt": next_day.isoformat()}},
            ],
        },
        {"_id": 0},
    ).to_list(10000)
    charge_total = round(sum(float(c.get("total") or c.get("amount") or 0) for c in daily_charges), 2)
    cash_total = round(payment_methods.get("cash", 0), 2)

    room_rate_rows = []
    occupied_booking_ids = {row.get("booking_id") for row in daily_in_house if row.get("booking_id")}
    for booking in all_bk:
        if booking.get("id") not in occupied_booking_ids:
            continue
        nights = max(1, (datetime.fromisoformat(_date_part(booking.get("check_out"))) - datetime.fromisoformat(_date_part(booking.get("check_in")))).days)
        actual_rate = float(booking.get("base_rate") or 0)
        if not actual_rate:
            actual_rate = float(booking.get("total_amount") or 0) / nights
        room = next((r for r in rooms if str(r.get("id")) == str(booking.get("room_id"))), {})
        base_rate = float(room.get("base_price") or room.get("price_per_night") or actual_rate or 0)
        room_rate_rows.append(
            {
                "booking_id": booking.get("id"),
                "room_number": str(booking.get("room_number") or room_map.get(str(booking.get("room_id"))) or "?").strip() or "?",
                "room_type": booking.get("room_type") or room.get("room_type"),
                "guest_name": _guest_display_name(guests_by_id.get(str(booking.get("guest_id"))), booking),
                "base_rate": round(base_rate, 2),
                "sold_rate": round(actual_rate, 2),
                "variance": round(actual_rate - base_rate, 2),
            }
        )

    prev_revenue = sum(charge_amount(charge) for charge in charges_between(previous_start, previous_end))
    prev_metrics = await load_stay_night_metrics(db, tenant_id, previous_start.date(), (previous_end - timedelta(days=1)).date())
    prev_room_nights = sum(row["occupied_rooms"] for row in prev_metrics)
    prev_room_revenue = sum(
        charge_amount(charge)
        for charge in charges_between(previous_start, previous_end)
        if str(charge.get("charge_category") or charge.get("charge_type") or "").lower() in {"room", "accommodation", "room_charge"}
    )
    prev_adr = round(prev_room_revenue / prev_room_nights, 2) if prev_room_nights > 0 else 0
    ly_revenue = sum(charge_amount(charge) for charge in charges_between(last_year_start, last_year_end))

    return {
        "date": today.strftime("%Y-%m-%d"),
        "summary": {
            "total_rooms": total_rooms,
            "occupied_rooms": occupied_today,
            "occupancy_percentage": occupancy_pct,
            "arrivals": arrivals,
            "departures": departures,
            "in_house": in_house,
            "no_shows": no_shows,
            "cancellations": cancellations,
            "today_revenue": round(today_revenue, 2),
            "adr": adr,
            "revpar": revpar,
            "fnb_revenue": round(fnb_revenue, 2),
        },
        "period_comparison": {
            "week_revenue": round(week_revenue, 2),
            "week_bookings": len(week_bookings),
            "month_revenue": round(month_revenue, 2),
            "month_bookings": len(month_bookings),
            "prev_month_revenue": round(prev_revenue, 2),
            "prev_month_bookings": len(prev_bookings),
            "prev_month_adr": prev_adr,
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
            "total": len(hk_tasks),
            "rows": sorted(housekeeping_rows, key=lambda row: (str(row.get("room_number") or ""), str(row.get("created_at") or ""))),
        },
        "front_cashier": {
            "charge_total": charge_total,
            "collection_total": round(total_paid, 2),
            "cash_total": cash_total,
            "non_cash_total": round(total_paid - cash_total, 2),
            "net_movement": round(total_paid - charge_total, 2),
            "charge_count": len(daily_charges),
            "payment_count": len(payment_rows),
        },
        "room_rate_control": room_rate_rows,
        "daily_analysis": {
            "date": target_day,
            "occupied_rooms": occupied_today,
            "total_rooms": total_rooms,
            "occupancy_percentage": occupancy_pct,
            "arrivals": arrivals,
            "departures": departures,
            "in_house_guests": len(daily_in_house),
            "room_revenue": round(today_revenue, 2),
            "adr": adr,
            "revpar": revpar,
            "collections": round(total_paid, 2),
        },
        "maintenance": {"open": maint_open, "completed_month": maint_completed},
        "finance": {"pending_invoices": pending_invoices, "paid_invoices_month": paid_invoices},
    }
