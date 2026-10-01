"""
PMS / Night Audit Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
+ Opera #8: Trial Balance / Daily Operations Resume — gece auditi sonrası tek özet rapor
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from common.context import OperationContext
from core.business_date_service import accounting_day_match
from core.security import (
    get_current_user,
)
from core.tenant_db import get_system_db
from domains.pms.night_audit_service import night_audit_service
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import load_stay_night_metrics

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Night Audit"])


@router.get("/audit-logs")
@cached(ttl=600, key_prefix="audit_logs")
async def get_audit_logs(
    entity_type: str | None = None,
    entity_id: str | None = None,
    user_id: str | None = None,
    action: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v86 DV: audit log admin/exec
):
    """Get audit logs with filters"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_audit_logs(ctx, entity_type, entity_id, user_id, action, start_date, end_date, limit)
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return result.data


@router.get("/logs/errors")
async def get_error_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    severity: str | None = None,
    endpoint: str | None = None,
    resolved: bool | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get error logs with filtering"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_error_logs(ctx, start_date, end_date, severity, endpoint, resolved, limit, skip)
    return result.data


@router.post("/logs/errors/{error_id}/resolve")
async def resolve_error_log(
    error_id: str,
    resolution_notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Mark error log as resolved"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.resolve_error_log(ctx, error_id, resolution_notes)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error)
    return result.data


@router.get("/logs/night-audit")
async def get_night_audit_logs(start_date: str | None = None, end_date: str | None = None, status: str | None = None, limit: int = 100, skip: int = 0, current_user: User = Depends(get_current_user)):
    """Get night audit logs"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_night_audit_logs(ctx, start_date, end_date, status, limit, skip)
    return result.data


@router.get("/logs/ota-sync")
async def get_ota_sync_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    channel: str | None = None,
    sync_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get OTA sync logs"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_ota_sync_logs(ctx, start_date, end_date, channel, sync_type, status, limit, skip)
    return result.data


@router.get("/logs/rms-publish")
async def get_rms_publish_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    publish_type: str | None = None,
    auto_published: bool | None = None,
    status: str | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get RMS publish logs"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_rms_publish_logs(ctx, start_date, end_date, publish_type, auto_published, status, limit, skip)
    return result.data


@router.get("/logs/maintenance-predictions")
async def get_maintenance_prediction_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    equipment_type: str | None = None,
    prediction_result: str | None = None,
    room_number: str | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get maintenance prediction logs"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_maintenance_prediction_logs(ctx, start_date, end_date, equipment_type, prediction_result, room_number, limit, skip)
    return result.data


# ─────────────────────────────────────────────────────────────────────────────
# Opera #8 — Trial Balance / Daily Operations Resume
# Gece auditi sonrası: gelir, ödemeler, doluluk, ADR/RevPAR, AR, depozito,
# açık folio'lar — tek bir özet ekran.
# ─────────────────────────────────────────────────────────────────────────────


async def _sum_payments(db, tid: str, business_date: str, start: str, end: str, by_method: bool = False):
    pipeline = [
        {
            "$match": {
                "tenant_id": tid,
                "voided": {"$ne": True},
                "status": {"$nin": ["void", "voided", "failed", "cancelled", "rejected"]},
                "payment_method": {"$nin": ["discount", "complimentary", "correction", "city_ledger", "ar"]},
                **accounting_day_match(
                    business_date,
                    {"payment_date": {"$gte": start, "$lt": end}},
                    {"processed_at": {"$gte": start, "$lt": end}},
                    {"created_at": {"$gte": start, "$lt": end}},
                ),
            }
        },
    ]
    if by_method:
        pipeline.append(
            {
                "$group": {
                    "_id": {"$ifNull": ["$payment_method", "other"]},
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1},
                }
            }
        )
    else:
        pipeline.append({"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}})
    return await db.payments.aggregate(pipeline).to_list(50)


async def _sum_charges(db, tid: str, business_date: str, start: str, end: str):
    """Folio_charges'dan kategori bazlı gelir."""
    return await db.folio_charges.aggregate(
        [
            {
                "$match": {
                    "tenant_id": tid,
                    "voided": {"$ne": True},
                    **accounting_day_match(
                        business_date,
                        {"posted_at": {"$gte": start, "$lt": end}},
                        {"date": {"$gte": start, "$lt": end}},
                        {"created_at": {"$gte": start, "$lt": end}},
                    ),
                }
            },
            {
                "$group": {
                    "_id": {"$ifNull": ["$category", "other"]},
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1},
                }
            },
        ]
    ).to_list(50)


ROOM_REVENUE_CATEGORIES = {"rooms", "room", "accommodation", "room_charge"}
FNB_REVENUE_CATEGORIES = {"fnb", "food", "beverage", "restaurant", "bar", "minibar", "room_service"}


def _daily_revenue_summary(metric_rows: list[dict], charges_by_cat: list[dict]) -> dict:
    """Reconcile posted folio revenue with the accrued occupied-room value.

    A current business day normally has no room posting until Night Audit. In
    that window, showing zero ADR/RevPAR is false; occupied-room accrual is the
    operational source of truth. Non-room folio charges remain posted values.
    """
    posted_by_category: dict[str, float] = {}
    for row in charges_by_cat:
        category = str(row.get("_id") or "other").strip().lower()
        posted_by_category[category] = round(posted_by_category.get(category, 0) + float(row.get("total") or 0), 2)

    posted_rooms = round(sum(value for key, value in posted_by_category.items() if key in ROOM_REVENUE_CATEGORIES), 2)
    occupied_room_nights = sum(int(row.get("occupied_rooms") or 0) for row in metric_rows)
    available_room_nights = sum(int(row.get("total_rooms") or 0) for row in metric_rows)
    accrued_rooms = round(sum(float(row.get("revenue") or 0) for row in metric_rows), 2)
    has_posting_gap = occupied_room_nights > 0 and posted_rooms == 0
    rooms = accrued_rooms if has_posting_gap else posted_rooms
    source = "accrued" if has_posting_gap else "posted"

    fnb = round(sum(value for key, value in posted_by_category.items() if key in FNB_REVENUE_CATEGORIES), 2)
    non_room_by_category = {
        key: value
        for key, value in posted_by_category.items()
        if key not in ROOM_REVENUE_CATEGORIES
    }
    other = round(sum(value for key, value in non_room_by_category.items() if key not in FNB_REVENUE_CATEGORIES), 2)
    return {
        "rooms": rooms,
        "posted_rooms": posted_rooms,
        "accrued_rooms": accrued_rooms,
        "room_revenue_source": source,
        "posting_pending": has_posting_gap,
        "fnb": fnb,
        "other": other,
        "by_category": non_room_by_category,
        "total": round(rooms + fnb + other, 2),
        "adr": round(rooms / occupied_room_nights, 2) if occupied_room_nights else 0.0,
        "revpar": round(rooms / available_room_nights, 2) if available_room_nights else 0.0,
    }


@router.get("/trial-balance")
async def trial_balance(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # finansal KPI: yetki şart
):
    """Günün özet bilançosu (Trial Balance / Daily Operations Resume).

    Opera Cloud'daki "Manager's Daily Resume" karşılığı:
      - Revenue (rooms, F&B, other) — folio_charges kategori bazında, business date
      - Payments by method (cash, card, bank, AR…) — payment_date filtre
      - Occupancy / ADR / RevPAR — bugün için canlı durum, geçmiş/gelecek için
        booking span'ına göre (check_in <= date < check_out)
      - Open folios, AR balance, deposit balance
      - Son night audit durumu
    """
    db = get_system_db()
    tid = current_user.tenant_id
    today = (date or datetime.now(UTC).date().isoformat())[:10]
    try:
        d = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as e:
        raise HTTPException(400, "Tarih formatı YYYY-MM-DD olmalı") from e
    day_start = d.isoformat()
    day_end = (d + timedelta(days=1)).isoformat()
    is_today = today == datetime.now(UTC).date().isoformat()

    # In-house = check_in <= day_end AND check_out > day_start
    # (gün içinde herhangi bir an otelde olan rezervasyon)
    in_house_q = {
        "tenant_id": tid,
        "check_in": {"$lt": day_end},
        "check_out": {"$gt": day_start},
        "status": {"$in": ["checked_in", "checked_out", "in_house"]},
    }

    (
        total_rooms,
        occupied_now,
        out_of_order,
        in_house_count,
        arrivals_count,
        departures_count,
        no_show_count,
        payments_by_method,
        charges_by_cat,
        ar_balance_doc,
        deposit_balance_doc,
        open_folios_count,
        last_audit,
        stay_metrics,
    ) = await asyncio.gather(
        db.rooms.count_documents({"tenant_id": tid}),
        db.rooms.count_documents({"tenant_id": tid, "status": "occupied"}),
        db.rooms.count_documents({"tenant_id": tid, "status": {"$in": ["ooo", "out_of_order", "maintenance"]}}),
        db.bookings.count_documents(in_house_q),
        db.bookings.count_documents(
            {
                "tenant_id": tid,
                "check_in": {"$gte": day_start, "$lt": day_end},
                "status": {"$in": ["checked_in", "in_house"]},
            }
        ),
        db.bookings.count_documents(
            {
                "tenant_id": tid,
                "check_out": {"$gte": day_start, "$lt": day_end},
                "status": "checked_out",
            }
        ),
        db.bookings.count_documents(
            {
                "tenant_id": tid,
                "check_in": {"$gte": day_start, "$lt": day_end},
                "status": "no_show",
            }
        ),
        _sum_payments(db, tid, today, day_start, day_end, by_method=True),
        _sum_charges(db, tid, today, day_start, day_end),
        db.bookings.aggregate(
            [
                {"$match": {"tenant_id": tid, "status": "checked_out", "ar_balance": {"$gt": 0}}},
                {"$group": {"_id": None, "total": {"$sum": "$ar_balance"}}},
            ]
        ).to_list(1),
        db.deposits.aggregate(
            [
                {"$match": {"tenant_id": tid, "status": {"$ne": "applied"}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
        ).to_list(1),
        db.folios.count_documents({"tenant_id": tid, "status": {"$ne": "closed"}}),
        db.night_audit_logs.find_one(
            {"tenant_id": tid},
            sort=[("created_at", -1)],
        ),
        load_stay_night_metrics(db, tid, d.date(), d.date(), actual_only=True),
    )

    revenue = _daily_revenue_summary(stay_metrics, charges_by_cat)
    total_revenue = revenue["total"]

    # Payment özeti
    pay_by_method: dict[str, dict] = {}
    total_payments = 0.0
    for p in payments_by_method:
        m = p["_id"] or "other"
        pay_by_method[m] = {"total": round(p["total"] or 0, 2), "count": p["count"]}
        total_payments += p["total"] or 0

    # Doluluk: bugün → canlı status; başka gün → in-house booking sayısı
    metric = stay_metrics[0] if stay_metrics else {}
    occupied = int(metric.get("occupied_rooms", occupied_now if is_today else in_house_count) or 0)
    report_total_rooms = int(metric.get("total_rooms", total_rooms) or 0)
    occupancy_basis = "actual_stay_nights"

    if report_total_rooms > 0:
        occ_pct = round(occupied / report_total_rooms * 100, 1)
        revpar = revenue["revpar"]
    else:
        occ_pct = 0.0
        revpar = 0.0
    adr = revenue["adr"]
    available = max(0, report_total_rooms - occupied - out_of_order) if report_total_rooms > 0 else 0

    in_balance = abs(total_revenue - total_payments) < 0.01

    last_audit_info = None
    if last_audit:
        last_audit.pop("_id", None)
        last_audit_info = {
            "status": last_audit.get("status"),
            "created_at": last_audit.get("created_at"),
            "audit_date": last_audit.get("audit_date"),
        }

    return {
        "date": today,
        "generated_at": datetime.now(UTC).isoformat(),
        "occupancy": {
            "total_rooms": report_total_rooms,
            "occupied": occupied,
            "out_of_order": out_of_order,
            "available": available,
            "occupancy_pct": occ_pct,
            "basis": occupancy_basis,
        },
        "movements": {
            "arrivals": arrivals_count,
            "departures": departures_count,
            "no_shows": no_show_count,
            "in_house": in_house_count,
        },
        "revenue": {
            **revenue,
            "adr": adr,
            "revpar": revpar,
        },
        "payments": {
            "by_method": pay_by_method,
            "total": round(total_payments, 2),
        },
        "ledger": {
            "ar_balance": round((ar_balance_doc[0]["total"] if ar_balance_doc else 0) or 0, 2),
            "deposit_balance": round((deposit_balance_doc[0]["total"] if deposit_balance_doc else 0) or 0, 2),
            "open_folios": open_folios_count,
        },
        "balance_check": {
            "revenue_minus_payments": round(total_revenue - total_payments, 2),
            "in_balance": in_balance,
        },
        "last_night_audit": last_audit_info,
    }
