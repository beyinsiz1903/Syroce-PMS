"""Auto-split from reports.py — backward-compatible sub-router."""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPBearer

security = HTTPBearer()

from core.business_date_service import accounting_day_match, ensure_business_date_initialized
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import (
    NON_COMMERCIAL_STATUSES,
    as_date,
    load_stay_night_metrics,
)

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


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"{field} YYYY-MM-DD formatında olmalı") from exc


async def _default_business_date(tenant_id: str) -> date:
    state = await ensure_business_date_initialized(db, tenant_id)
    return _parse_date(state["business_date"], "business_date")


def _effective_payment(payment: dict) -> float:
    status = str(payment.get("status") or "paid").strip().lower()
    if payment.get("voided") or status in {"void", "voided", "failed", "cancelled", "rejected"}:
        return 0.0
    amount = float(payment.get("amount") or 0)
    if str(payment.get("payment_type") or "").lower() == "refund" and amount > 0:
        amount = -amount
    return amount


@sub_router.get("/reports/occupancy")
@cached(ttl=600, key_prefix="report_occupancy")  # Cache for 10 minutes
async def get_occupancy_report(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
    _nocache: bool = Query(False, alias="nocache"),
):
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if start > end:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Başlangıç tarihi bitiş tarihinden sonra olamaz")
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, start, end, actual_only=True)
    total_room_nights = sum(row["total_rooms"] for row in metrics)
    occupied_room_nights = sum(row["occupied_rooms"] for row in metrics)
    occupancy_rate = round((occupied_room_nights / total_room_nights * 100), 2) if total_room_nights else 0
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_rooms": metrics[0]["total_rooms"] if metrics else 0,
        "total_room_nights": total_room_nights,
        "occupied_room_nights": occupied_room_nights,
        "occupancy_rate": occupancy_rate,
        "days": metrics,
    }


@sub_router.get("/reports/revenue")
@cached(ttl=600, key_prefix="report_revenue")  # Cache for 10 minutes
async def get_revenue_report(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
    _nocache: bool = Query(False, alias="nocache"),
):
    end = _parse_date(end_date, "end_date") if end_date else await _default_business_date(current_user.tenant_id)
    start = _parse_date(start_date, "start_date") if start_date else end - timedelta(days=29)
    if start > end:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Başlangıç tarihi bitiş tarihinden sonra olamaz")
    start_date, end_date = start.isoformat(), end.isoformat()
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, start, end, actual_only=True)
    room_nights = sum(row["occupied_rooms"] for row in metrics)
    available_room_nights = sum(row["total_rooms"] for row in metrics)
    folio_charges = await db.folio_charges.find(
        {
            "tenant_id": current_user.tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"business_date": {"$gte": start_date, "$lte": end_date}},
                {"business_date": {"$exists": False}, "date": {"$gte": start_date, "$lt": (end + timedelta(days=1)).isoformat()}},
                {"business_date": None, "date": {"$gte": start_date, "$lt": (end + timedelta(days=1)).isoformat()}},
            ],
        },
        {"_id": 0},
    ).to_list(1000)
    extra_charges = await db.extra_charges.find(
        {
            "tenant_id": current_user.tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"business_date": {"$gte": start_date, "$lte": end_date}},
                {"business_date": {"$exists": False}, "charge_date": {"$gte": start_date, "$lt": (end + timedelta(days=1)).isoformat()}},
                {"business_date": {"$exists": False}, "date": {"$gte": start_date, "$lt": (end + timedelta(days=1)).isoformat()}},
                {"business_date": {"$exists": False}, "created_at": {"$gte": start_date, "$lt": (end + timedelta(days=1)).isoformat()}},
                {"business_date": None, "created_at": {"$gte": start_date, "$lt": (end + timedelta(days=1)).isoformat()}},
            ],
        },
        {"_id": 0},
    ).to_list(1000)
    revenue_by_type: dict[str, float] = {}
    for charge in [*folio_charges, *extra_charges]:
        charge_type = charge.get("charge_category") or charge.get("category") or charge.get("charge_type") or "other"
        amount = charge.get("total")
        if amount is None:
            amount = charge.get("charge_amount")
        if amount is None:
            amount = charge.get("amount") or 0
        revenue_by_type[charge_type] = revenue_by_type.get(charge_type, 0.0) + float(amount)
    revenue_by_type = {key: round(value, 2) for key, value in revenue_by_type.items()}
    total_revenue = round(sum(revenue_by_type.values()), 2)
    room_revenue = sum(value for key, value in revenue_by_type.items() if key in {"room", "accommodation", "room_charge"})
    arrivals = await db.bookings.count_documents(
        {"tenant_id": current_user.tenant_id, "check_in": {"$gte": start_date, "$lt": (end + timedelta(days=1)).isoformat()}, "status": {"$nin": list(NON_COMMERCIAL_STATUSES)}}
    )
    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_revenue": round(total_revenue, 2),
        "room_nights_sold": room_nights,
        "adr": round(room_revenue / room_nights, 2) if room_nights else 0,
        "rev_par": round(room_revenue / available_room_nights, 2) if available_room_nights else 0,
        "revenue_by_type": revenue_by_type,
        "bookings_count": arrivals,
        "revenue_basis": "posted_folio_and_reservation_charges",
    }


@sub_router.get("/reports/daily-summary")
@cached(ttl=30, key_prefix="report_daily_summary")  # Cache for 30 seconds
async def get_daily_summary(
    date_str: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
    _nocache: bool = Query(False, alias="nocache"),
):
    target_date = _parse_date(date_str, "date_str") if date_str else await _default_business_date(current_user.tenant_id)
    day = target_date.isoformat()
    next_day = (target_date + timedelta(days=1)).isoformat()
    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "$or": [{"check_in": {"$gte": day, "$lt": next_day}}, {"check_out": {"$gte": day, "$lt": next_day}}, {"check_in": {"$lte": day}, "check_out": {"$gt": day}}]},
        {"_id": 0, "status": 1, "check_in": 1, "check_out": 1, "checked_in_at": 1, "checked_out_at": 1},
    ).to_list(10000)
    arrivals = sum(1 for booking in bookings if as_date(booking.get("check_in")) == target_date and str(booking.get("status") or "").lower() not in NON_COMMERCIAL_STATUSES)
    departures = sum(1 for booking in bookings if as_date(booking.get("check_out")) == target_date and str(booking.get("status") or "").lower() not in NON_COMMERCIAL_STATUSES)
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, target_date, target_date, actual_only=True)
    inhouse = metrics[0]["occupied_rooms"] if metrics else 0
    total_rooms = metrics[0]["total_rooms"] if metrics else 0
    payments = await db.payments.find(
        {
            "tenant_id": current_user.tenant_id,
            **accounting_day_match(
                day,
                {"processed_at": {"$regex": f"^{day}"}},
                {"payment_date": day},
                {"date": day},
                {"created_at": {"$regex": f"^{day}"}},
            ),
        },
        {"_id": 0},
    ).to_list(10000)
    collections = sum(_effective_payment(payment) for payment in payments)
    return {
        "date": target_date.isoformat(),
        "arrivals": arrivals,
        "departures": departures,
        "inhouse": inhouse,
        "total_rooms": total_rooms,
        "occupancy_rate": round(min((inhouse / total_rooms * 100), 100.0) if total_rooms > 0 else 0, 2),
        "collections": round(collections, 2),
        "daily_revenue": round(collections, 2),
        "daily_revenue_deprecated": True,
    }


@sub_router.get("/reports/forecast")
@cached(ttl=900, key_prefix="report_forecast")  # Cache for 15 min
async def get_forecast(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
    _nocache: bool = Query(False, alias="nocache"),
):
    if days < 1 or days > 366:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="days 1 ile 366 arasında olmalı")
    today = await _default_business_date(current_user.tenant_id)
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, today, today + timedelta(days=days - 1))
    return [
        {
            "date": row["date"],
            "bookings": row["occupied_rooms"],
            "total_rooms": row["total_rooms"],
            "occupancy_rate": row["occupancy_rate"],
            "expected_revenue": row["revenue"],
        }
        for row in metrics
    ]
