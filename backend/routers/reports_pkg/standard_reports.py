"""Auto-split from reports.py — backward-compatible sub-router."""

import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPBearer

security = HTTPBearer()

from core.business_date_service import accounting_day_match, accounting_period_match, ensure_business_date_initialized
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.report_money import currency_code
from modules.pms_core.reporting_financials import deduplicate_report_payments, effective_collection, effective_revenue_adjustment
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
    return currency_code(row.get("currency"))


def _charge_amount(row: dict) -> float:
    for field in ("total", "charge_amount", "amount"):
        if row.get(field) is not None:
            return float(row[field] or 0)
    return 0.0


def _charge_category(row: dict) -> str:
    category = str(row.get("charge_category") or row.get("category") or row.get("charge_type") or "other").strip().lower()
    return "room" if category in {"room", "room_charge", "accommodation", "lodging", "konaklama"} else category


def _single_currency_value(totals: dict[str, float]) -> float | None:
    nonzero = [float(value) for value in totals.values() if float(value) != 0]
    return round(nonzero[0], 2) if len(nonzero) == 1 else (0.0 if not nonzero else None)


async def _posted_revenue_rows(tenant_id: str, start: date, end: date, *, database=None) -> list[dict]:
    """Return posted folio, manual-extra and untransferred POS revenue once."""
    start_text = start.isoformat()
    next_day = (end + timedelta(days=1)).isoformat()
    database = database if database is not None else db
    period = {"$gte": start_text, "$lt": next_day}
    bson_period = {"$gte": datetime.combine(start, time.min, UTC), "$lt": datetime.combine(end + timedelta(days=1), time.min, UTC)}

    def legacy_period(field, *missing):
        return {**{key: {"$in": [None, ""]} for key in missing},
            "$or": [{field: period}, {field: bson_period}]}
    charge_query = {
        "tenant_id": tenant_id,
        "voided": {"$ne": True},
        **accounting_period_match(start_text, end.isoformat(),
            legacy_period("date"), legacy_period("charge_date", "date"), legacy_period("created_at", "date", "charge_date")),
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
        "business_date": 1,
        "date": 1,
        "charge_date": 1,
        "created_at": 1,
    }
    folio_rows, extra_rows, pos_rows = await asyncio.gather(
        # Financial reports may cover high-volume F&B and chain properties.
        # A hard cap silently underreports revenue, so preserve every matching
        # ledger row instead of treating 10,000 as a reporting limit.
        database.folio_charges.find(charge_query, projection).to_list(None),
        database.extra_charges.find(charge_query, projection).to_list(None),
        database.pos_orders.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": ["closed", "completed", "paid"]},
                **accounting_period_match(start_text, end.isoformat(),
                    legacy_period("closed_at"), legacy_period("created_at", "closed_at")),
            },
            {"_id": 0, "id": 1, "total_amount": 1, "grand_total": 1, "currency": 1, "business_date": 1, "closed_at": 1, "created_at": 1},
        ).to_list(None),
    )
    # Finalized POS ledger is authoritative; orders are only a legacy fallback.
    # In particular, refunds belong to their own accounting day, never as a
    # cumulative subtraction from the original order's historical sales day.
    transaction_query = {"tenant_id": tenant_id,
        "status": {"$in": ["completed", "closed", "paid", "refunded", "refund"]},
        **accounting_period_match(start_text, end.isoformat(),
            legacy_period("transaction_date"), legacy_period("created_at", "transaction_date"))}
    transaction_sources = await asyncio.gather(
        database.pos_transactions.find(transaction_query, {"_id": 0}).to_list(None),
        database.pos_menu_transactions.find(transaction_query, {"_id": 0}).to_list(None),
        database.transactions.find({**transaction_query, "$and": [{"$or": [{"category": "pos"}, {"_closure_source": "pos_menu_transactions"}]}]}, {"_id": 0}).to_list(None),
    )
    represented_pos_ids = {str(row["source_pos_order_id"]) for row in [*folio_rows, *extra_rows] if row.get("source_pos_order_id")}
    settled_ids, seen_transaction_ids, order_source = set(), set(), {}
    transaction_rows = []
    order_currencies = {str(row.get("id")): row.get("currency") for row in pos_rows}
    for transactions in transaction_sources:
        for row in transactions:
            if row.get("order_id") and row.get("currency"):
                order_currencies[str(row["order_id"])] = row["currency"]
    unresolved = {str(row["order_id"]) for transactions in transaction_sources for row in transactions
        if row.get("order_id") and not row.get("currency") and not order_currencies.get(str(row["order_id"]))}
    if unresolved:
        # A refund may be inside this report while its original sale is not.
        # Recover currency from the tenant-scoped source order, not from today
        # or a different currency's sales on the selected day.
        source_orders = await database.pos_orders.find({"tenant_id": tenant_id, "id": {"$in": sorted(unresolved)}}, {"_id": 0, "id": 1, "currency": 1}).to_list(None)
        order_currencies.update({str(row["id"]): row.get("currency") for row in source_orders})
    for source_index, transactions in enumerate(transaction_sources):
        for row in transactions:
            transaction_id = str(row.get("id") or row.get("transaction_id") or "")
            order_id = str(row.get("order_id") or "")
            if order_id:
                settled_ids.add(order_id)
                if order_source.setdefault(order_id, source_index) != source_index:
                    continue
            if transaction_id and transaction_id in seen_transaction_ids:
                continue
            if transaction_id:
                seen_transaction_ids.add(transaction_id)
            # Room transfers are already revenue in the folio ledger. Do not
            # reintroduce an asynchronously reversed/voided charge as cash POS.
            if order_id in represented_pos_ids or row.get("payment_method") == "room_charge":
                continue
            value = row.get("total_amount") if row.get("total_amount") is not None else row.get("amount", 0)
            value = float(value or 0) - float(row.get("tip_amount") or 0)
            if row.get("payment_type") == "refund" or row.get("status") in {"refunded", "refund"}:
                value = -abs(value)
            transaction_rows.append({"category": "fnb", "total": value,
                "currency": row.get("currency") or order_currencies.get(order_id) or "TRY",
                "business_date": row.get("business_date") or row.get("transaction_date"), "date": row.get("created_at")})
    direct_pos_rows = [
        {
            "category": "fnb",
            "total": row.get("grand_total") if row.get("grand_total") is not None else row.get("total_amount", 0),
            "currency": row.get("currency") or "TRY",
            "business_date": row.get("business_date"),
            "date": row.get("closed_at") or row.get("created_at"),
        }
        for row in pos_rows
        if str(row.get("id") or "") not in represented_pos_ids | settled_ids
    ]
    return [*folio_rows, *extra_rows, *transaction_rows, *direct_pos_rows]


@sub_router.get("/reports/occupancy")
@cached(ttl=600, key_prefix="report_occupancy_v2")
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
@cached(ttl=600, key_prefix="report_revenue_v2")
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
    for payment in deduplicate_report_payments(payments):
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
@cached(ttl=900, key_prefix="report_forecast_v2")
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
