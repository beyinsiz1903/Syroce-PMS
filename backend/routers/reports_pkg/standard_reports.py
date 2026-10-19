"""Auto-split from reports.py — backward-compatible sub-router."""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPBearer

security = HTTPBearer()

from core.business_date_service import ensure_business_date_initialized
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.report_money import add_amount, currency_code, money, resolve_ledger_currencies, rounded, rounded_totals
from modules.pms_core.reporting_dates import date_period_match
from modules.pms_core.reporting_financials import deduplicate_report_payments, effective_collection, effective_revenue_adjustment, report_payment_day_match
from modules.pms_core.reporting_ledger import charge_amount as _charge_amount
from modules.pms_core.reporting_ledger import charge_category as _charge_category
from modules.pms_core.reporting_ledger import posted_revenue_rows
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import (
    NON_COMMERCIAL_STATUSES,
    as_date,
    load_stay_night_metrics,
    stay_day_match,
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
    return currency_code(row.get("currency"))




def _single_currency_value(totals: dict[str, float]) -> float | None:
    nonzero = [float(value) for value in totals.values() if float(value) != 0]
    return round(nonzero[0], 2) if len(nonzero) == 1 else (0.0 if not nonzero else None)


async def _posted_revenue_rows(tenant_id: str, start: date, end: date, *, database=None) -> list[dict]:
    return await posted_revenue_rows(tenant_id, start, end, database=database if database is not None else db)


@sub_router.get("/reports/occupancy")
@cached(ttl=600, key_prefix="report_occupancy_v4")
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
@cached(ttl=600, key_prefix="report_revenue_v3")
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
        charge_type = _charge_category(charge)
        amount = _charge_amount(charge)
        currency = _currency_code(charge)
        add_amount(revenue_by_type_currency.setdefault(charge_type, {}), currency, amount)
        add_amount(total_revenue_by_currency, currency, amount)
        if charge_type in {"room", "accommodation", "room_charge"}:
            add_amount(room_revenue_by_currency, currency, amount)
    revenue_by_type_currency = {
        category: rounded_totals(totals)
        for category, totals in revenue_by_type_currency.items()
    }
    # Legacy scalar fields are populated only for a true single-currency report.
    # They must never be the arithmetic sum of unlike currencies.
    for charge_type, totals in revenue_by_type_currency.items():
        value = _single_currency_value(totals)
        revenue_by_type[charge_type] = value if value is not None else 0.0
    revenue_by_type = {key: round(value, 2) for key, value in revenue_by_type.items()}
    total_revenue_by_currency = rounded_totals(total_revenue_by_currency)
    room_revenue_by_currency = rounded_totals(room_revenue_by_currency)
    total_revenue = _single_currency_value(total_revenue_by_currency)
    room_revenue = _single_currency_value(room_revenue_by_currency)
    adr_by_currency = {
        currency: rounded(money(amount) / sold_room_nights) if sold_room_nights else 0.0
        for currency, amount in room_revenue_by_currency.items()
    }
    rev_par_by_currency = {
        currency: rounded(money(amount) / available_room_nights) if available_room_nights else 0.0
        for currency, amount in room_revenue_by_currency.items()
    }
    arrivals = await db.bookings.count_documents(
        {"tenant_id": current_user.tenant_id, **date_period_match("check_in", start, end), "status": {"$nin": list(NON_COMMERCIAL_STATUSES)}}
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
@cached(ttl=30, key_prefix="report_daily_summary_v2")
async def get_daily_summary(
    date_str: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
    _nocache: bool = Query(False, alias="nocache"),
):
    target_date = _parse_date(date_str, "date_str") if date_str else await _default_business_date(current_user.tenant_id)
    day = target_date.isoformat()
    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, **stay_day_match(target_date)},
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
            **report_payment_day_match(day),
        },
        {"_id": 0},
    ).to_list(None)
    payments = await resolve_ledger_currencies(payments, current_user.tenant_id, database=db)
    collections_by_currency: dict[str, float] = {}
    adjustments_by_currency: dict[str, float] = {}
    for payment in deduplicate_report_payments(payments):
        currency = _currency_code(payment)
        add_amount(collections_by_currency, currency, _effective_payment(payment))
        add_amount(adjustments_by_currency, currency, effective_revenue_adjustment(payment))
    collections_by_currency = rounded_totals(collections_by_currency)
    adjustments_by_currency = {currency: amount for currency, amount in rounded_totals(adjustments_by_currency).items() if amount}
    posted_rows = await _posted_revenue_rows(current_user.tenant_id, target_date, target_date)
    posted_revenue_by_currency: dict[str, float] = {}
    for row in posted_rows:
        currency = _currency_code(row)
        add_amount(posted_revenue_by_currency, currency, _charge_amount(row))
    gross_posted_revenue_by_currency = rounded_totals(posted_revenue_by_currency)
    for currency, adjustment in adjustments_by_currency.items():
        add_amount(posted_revenue_by_currency, currency, -adjustment)
    posted_revenue_by_currency = rounded_totals(posted_revenue_by_currency)
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
@cached(ttl=900, key_prefix="report_forecast_v4")
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
            "expected_revenue_by_currency": row.get("revenue_by_currency", {}),
            "mixed_currency": row.get("mixed_currency", False),
        }
        for row in metrics
    ]
