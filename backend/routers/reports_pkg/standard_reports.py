"""Auto-split from reports.py — backward-compatible sub-router."""

import asyncio
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
from modules.pms_core.reporting_financials import effective_collection, effective_revenue_adjustment
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
    return effective_collection(payment)


def _currency_code(row: dict) -> str:
    return str(row.get("currency") or "TRY").strip().upper() or "TRY"


def _charge_amount(row: dict) -> float:
    for field in ("total", "charge_amount", "amount"):
        if row.get(field) is not None:
            return float(row[field] or 0)
    return 0.0


def _single_currency_value(totals: dict[str, float]) -> float | None:
    nonzero = [float(value) for value in totals.values() if float(value) != 0]
    return round(nonzero[0], 2) if len(nonzero) == 1 else (0.0 if not nonzero else None)


async def _posted_revenue_rows(tenant_id: str, start: date, end: date) -> list[dict]:
    """Return posted folio, manual-extra and untransferred POS revenue once."""
    start_text = start.isoformat()
    next_day = (end + timedelta(days=1)).isoformat()
    charge_query = {
        "tenant_id": tenant_id,
        "voided": {"$ne": True},
        "$or": [
            {"business_date": {"$gte": start_text, "$lt": next_day}},
            {"business_date": {"$exists": False}, "date": {"$gte": start_text, "$lt": next_day}},
            {"business_date": None, "date": {"$gte": start_text, "$lt": next_day}},
            {"business_date": {"$exists": False}, "charge_date": {"$gte": start_text, "$lt": next_day}},
            {"business_date": {"$exists": False}, "created_at": {"$gte": start_text, "$lt": next_day}},
            {"business_date": None, "created_at": {"$gte": start_text, "$lt": next_day}},
        ],
    }
    projection = {
        "_id": 0,
        "charge_category": 1,
        "category": 1,
        "charge_type": 1,
        "total": 1,
        "charge_amount": 1,
        "amount": 1,
        "currency": 1,
        "source_pos_order_id": 1,
    }
    folio_rows, extra_rows, pos_rows = await asyncio.gather(
        # Financial reports may cover high-volume F&B and chain properties.
        # A hard cap silently underreports revenue, so preserve every matching
        # ledger row instead of treating 10,000 as a reporting limit.
        db.folio_charges.find(charge_query, projection).to_list(None),
        db.extra_charges.find(charge_query, projection).to_list(None),
        db.pos_orders.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": ["closed", "completed", "served", "paid"]},
                "$or": [
                    {"business_date": {"$gte": start_text, "$lt": next_day}},
                    {"closed_at": {"$gte": start_text, "$lt": next_day}},
                    {"created_at": {"$gte": start_text, "$lt": next_day}},
                ],
            },
            {"_id": 0, "id": 1, "total_amount": 1, "grand_total": 1, "currency": 1},
        ).to_list(None),
    )
    represented_pos_ids = {str(row["source_pos_order_id"]) for row in folio_rows if row.get("source_pos_order_id")}
    direct_pos_rows = [
        {
            "category": "fnb",
            "total": row.get("total_amount") if row.get("total_amount") is not None else row.get("grand_total", 0),
            "currency": row.get("currency") or "TRY",
        }
        for row in pos_rows
        if str(row.get("id") or "") not in represented_pos_ids
    ]
    return [*folio_rows, *extra_rows, *direct_pos_rows]


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
    sold_room_nights = sum(row.get("sold_rooms", row["occupied_rooms"]) for row in metrics)
    available_room_nights = sum(row["total_rooms"] for row in metrics)
    revenue_rows = await _posted_revenue_rows(current_user.tenant_id, start, end)
    revenue_by_type: dict[str, float] = {}
    revenue_by_type_currency: dict[str, dict[str, float]] = {}
    total_revenue_by_currency: dict[str, float] = {}
    room_revenue_by_currency: dict[str, float] = {}
    for charge in revenue_rows:
        charge_type = charge.get("charge_category") or charge.get("category") or charge.get("charge_type") or "other"
        amount = _charge_amount(charge)
        currency = _currency_code(charge)
        revenue_by_type_currency.setdefault(charge_type, {})[currency] = revenue_by_type_currency.setdefault(charge_type, {}).get(currency, 0.0) + amount
        total_revenue_by_currency[currency] = total_revenue_by_currency.get(currency, 0.0) + amount
        if charge_type in {"room", "accommodation", "room_charge"}:
            room_revenue_by_currency[currency] = room_revenue_by_currency.get(currency, 0.0) + amount
    revenue_by_type_currency = {
        category: {currency: round(amount, 2) for currency, amount in totals.items()}
        for category, totals in revenue_by_type_currency.items()
    }
    # Legacy scalar fields are populated only for a true single-currency report.
    # They must never be the arithmetic sum of unlike currencies.
    for charge_type, totals in revenue_by_type_currency.items():
        value = _single_currency_value(totals)
        revenue_by_type[charge_type] = value if value is not None else 0.0
    revenue_by_type = {key: round(value, 2) for key, value in revenue_by_type.items()}
    total_revenue_by_currency = {key: round(value, 2) for key, value in total_revenue_by_currency.items()}
    room_revenue_by_currency = {key: round(value, 2) for key, value in room_revenue_by_currency.items()}
    total_revenue = _single_currency_value(total_revenue_by_currency)
    room_revenue = _single_currency_value(room_revenue_by_currency)
    adr_by_currency = {
        currency: round(amount / sold_room_nights, 2) if sold_room_nights else 0.0
        for currency, amount in room_revenue_by_currency.items()
    }
    rev_par_by_currency = {
        currency: round(amount / available_room_nights, 2) if available_room_nights else 0.0
        for currency, amount in room_revenue_by_currency.items()
    }
    arrivals = await db.bookings.count_documents(
        {"tenant_id": current_user.tenant_id, "check_in": {"$gte": start_date, "$lt": (end + timedelta(days=1)).isoformat()}, "status": {"$nin": list(NON_COMMERCIAL_STATUSES)}}
    )
    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_revenue": total_revenue,
        "total_revenue_by_currency": total_revenue_by_currency,
        "room_revenue": room_revenue,
        "room_revenue_by_currency": room_revenue_by_currency,
        "room_nights_sold": sold_room_nights,
        "adr": _single_currency_value(adr_by_currency),
        "adr_by_currency": adr_by_currency,
        "rev_par": _single_currency_value(rev_par_by_currency),
        "rev_par_by_currency": rev_par_by_currency,
        "revenue_by_type": revenue_by_type,
        "revenue_by_type_currency": revenue_by_type_currency,
        "mixed_currency": len([value for value in total_revenue_by_currency.values() if value]) > 1,
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
    ).to_list(None)
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
    ).to_list(None)
    collections_by_currency: dict[str, float] = {}
    adjustments_by_currency: dict[str, float] = {}
    for payment in payments:
        currency = _currency_code(payment)
        collections_by_currency[currency] = collections_by_currency.get(currency, 0.0) + _effective_payment(payment)
        adjustments_by_currency[currency] = adjustments_by_currency.get(currency, 0.0) + effective_revenue_adjustment(payment)
    collections_by_currency = {currency: round(amount, 2) for currency, amount in collections_by_currency.items()}
    adjustments_by_currency = {currency: round(amount, 2) for currency, amount in adjustments_by_currency.items() if amount}
    posted_rows = await _posted_revenue_rows(current_user.tenant_id, target_date, target_date)
    posted_revenue_by_currency: dict[str, float] = {}
    for row in posted_rows:
        currency = _currency_code(row)
        posted_revenue_by_currency[currency] = posted_revenue_by_currency.get(currency, 0.0) + _charge_amount(row)
    gross_posted_revenue_by_currency = {
        currency: round(amount, 2) for currency, amount in posted_revenue_by_currency.items()
    }
    for currency, adjustment in adjustments_by_currency.items():
        posted_revenue_by_currency[currency] = posted_revenue_by_currency.get(currency, 0.0) - adjustment
    posted_revenue_by_currency = {currency: round(amount, 2) for currency, amount in posted_revenue_by_currency.items()}
    return {
        "date": target_date.isoformat(),
        "arrivals": arrivals,
        "departures": departures,
        "inhouse": inhouse,
        "total_rooms": total_rooms,
        "occupancy_rate": round(min((inhouse / total_rooms * 100), 100.0) if total_rooms > 0 else 0, 2),
        "collections": _single_currency_value(collections_by_currency),
        "collections_by_currency": collections_by_currency,
        "daily_revenue": _single_currency_value(posted_revenue_by_currency),
        "daily_revenue_by_currency": posted_revenue_by_currency,
        "gross_posted_revenue_by_currency": gross_posted_revenue_by_currency,
        "revenue_adjustments_by_currency": adjustments_by_currency,
        "daily_revenue_basis": "posted_folio_and_pos_charges_net_of_financial_adjustments",
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
