"""
Travel Agent AR/AP Router
=========================
Endpoints for tracking agency receivables, payables, commissions,
payment plans, aging reports, and transaction history.

All endpoints under /api/agent-arap/
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v80 Bug DP

# Chain-scoped queries bypass per-tenant guard; we re-apply the chain filter
# ourselves via _chain_tenant_ids() (same pattern as routers/cross_property.py)
_sys_db = get_system_db()


async def _chain_tenant_ids(current_user: User) -> list[str]:
    """Tenant id'lerini zincir bazlı çöz: super_admin → hepsi,
    chain_id varsa → kardeşler, yoksa → sadece kendi tenant'ı.

    Sonuçta her zaman kullanıcının kendi tenant'ı dahildir (tenants
    koleksiyonunda doc'u olmasa bile)."""
    from core.security import _is_super_admin

    own_tid = current_user.tenant_id

    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in items:
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    if _is_super_admin(current_user):
        cursor = _sys_db.tenants.find({}, {"_id": 0, "tenant_id": 1})
        ids = [t["tenant_id"] async for t in cursor if t.get("tenant_id")]
        # Süper-admin'in kendi tenant'ı tenants koleksiyonunda eksik olabilir
        # (legacy demo seed) — dahil etmek garanti.
        return _dedupe([own_tid, *ids])
    own = await _sys_db.tenants.find_one(
        {"tenant_id": own_tid},
        {"_id": 0, "chain_id": 1},
    )
    chain_id = (own or {}).get("chain_id")
    if not chain_id:
        return [own_tid]
    cursor = _sys_db.tenants.find({"chain_id": chain_id}, {"_id": 0, "tenant_id": 1})
    ids = [t["tenant_id"] async for t in cursor if t.get("tenant_id")]
    return _dedupe([own_tid, *ids])


async def _tenant_name_map(tenant_ids: list[str]) -> dict[str, str]:
    cursor = _sys_db.tenants.find(
        {"tenant_id": {"$in": tenant_ids}},
        {"_id": 0, "tenant_id": 1, "hotel_name": 1, "name": 1, "property_name": 1},
    )
    out: dict[str, str] = {}
    async for t in cursor:
        tid = t.get("tenant_id")
        if tid:
            out[tid] = t.get("hotel_name") or t.get("property_name") or t.get("name") or tid
    return out


try:
    from cache_manager import cache, cached
except ImportError:  # pragma: no cover
    cache = None

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


def _invalidate_arap(tenant_id: str):
    """Sprint 33 R6: invalidate agent_arap_summary cache after AR/AP mutation."""
    if cache is not None and tenant_id:
        try:
            cache.safe_invalidate(tenant_id, "agent_arap_summary")
        except Exception:  # pragma: no cover
            pass


router = APIRouter(prefix="/api/agent-arap", tags=["travel-agent-arap"])


def _currency_code(value: Any, fallback: str = "TRY") -> str:
    code = str(value or fallback or "TRY").strip().upper()
    return code if len(code) == 3 and code.isalpha() else str(fallback or "TRY").upper()


def _round_currency_map(values: dict[str, Any] | None) -> dict[str, float]:
    return {_currency_code(currency): round(float(amount or 0), 2) for currency, amount in (values or {}).items() if abs(float(amount or 0)) > 0.000001}


def _add_currency(target: dict[str, float], currency: Any, amount: Any, fallback: str = "TRY") -> None:
    code = _currency_code(currency, fallback)
    target[code] = target.get(code, 0.0) + float(amount or 0)


def _sum_currency_maps(rows: list[dict], field: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        for currency, amount in (row.get(field) or {}).items():
            _add_currency(totals, currency, amount)
    return _round_currency_map(totals)


def _single_currency_amount(values: dict[str, Any] | None) -> float:
    """Legacy scalar compatibility without silently mixing currencies."""
    rounded = _round_currency_map(values)
    return next(iter(rounded.values()), 0.0) if len(rounded) == 1 else 0.0


def _oldest_date(values: list[Any]) -> Any | None:
    """Return the oldest parseable value even when legacy rows mix types."""
    parsed: list[tuple[datetime, Any]] = []
    for value in values:
        if not value:
            continue
        try:
            candidate = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
            if candidate.tzinfo is None:
                candidate = candidate.replace(tzinfo=UTC)
            parsed.append((candidate, value))
        except (ValueError, TypeError, AttributeError):
            continue
    return min(parsed, key=lambda item: item[0])[1] if parsed else None


class RecordPaymentRequest(BaseModel):
    agency_id: str
    amount: float = Field(..., gt=0)
    payment_method: str = "bank_transfer"
    reference: str = ""
    notes: str = ""
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class CreatePaymentPlanRequest(BaseModel):
    agency_id: str
    total_amount: float = Field(..., gt=0)
    installments: int = Field(..., ge=2, le=24)
    start_date: str
    notes: str = ""
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class UpdatePaymentPlanInstallment(BaseModel):
    plan_id: str
    installment_index: int = Field(..., ge=0)
    paid: bool = True
    payment_reference: str = ""


async def _get_agency_ledger(
    tenant_id: str,
    agency_id: str | None = None,
    db_handle=None,
) -> list[dict]:
    """Agency ledger'ı hesaplar.

    `db_handle` parametresi opsiyonel: chain bazlı çağrılarda `_sys_db`
    geçilir (tenant-guard bypass) — aksi takdirde mevcut request'in
    tenant-scoped `db` handle'ı kullanılır.
    """
    _db = db_handle if db_handle is not None else db
    tenant_currency, _ = await get_tenant_currency(tenant_id)
    tenant_currency = _currency_code(tenant_currency)
    match = {"tenant_id": tenant_id}
    if agency_id:
        match["id"] = agency_id

    agencies = await _db.agencies.find(
        {**match, "status": {"$ne": "deleted"}},
    ).to_list(500)

    if not agencies:
        return []

    # ── Perf: server-side aggregation (limit-siz, finans doğruluğu için kritik)
    # Eski sürüm N+1: agency başına 3 ardışık query → 26s/100 agency.
    # Yeni sürüm 3 paralel $group aggregation; hesap MongoDB'de yapılır,
    # Python'a sadece per-agency özet gelir → ölçekten bağımsız doğruluk.
    aids = [a["id"] for a in agencies]
    import asyncio as _asyncio

    bookings_pipe = [
        {"$match": {"tenant_id": tenant_id, "agency_id": {"$in": aids}, "status": {"$nin": ["cancelled"]}}},
        {
            "$group": {
                "_id": {
                    "agency_id": "$agency_id",
                    "currency": {"$toUpper": {"$ifNull": ["$currency", tenant_currency]}},
                },
                "total_revenue": {"$sum": {"$ifNull": ["$total_amount", 0]}},
                "count": {"$sum": 1},
                # Oldest unpaid: bekleyen status'lardaki en eski created_at
                "oldest_pending_created_at": {
                    "$min": {
                        "$cond": [
                            {"$in": ["$status", ["confirmed", "guaranteed", "checked_out"]]},
                            "$created_at",
                            None,
                        ]
                    }
                },
            }
        },
    ]
    txns_pipe = [
        {"$match": {"tenant_id": tenant_id, "agency_id": {"$in": aids}}},
        {
            "$group": {
                "_id": {
                    "agency_id": "$agency_id",
                    "currency": {"$toUpper": {"$ifNull": ["$currency", tenant_currency]}},
                },
                "total_paid": {"$sum": {"$cond": [{"$eq": ["$type", "payment"]}, {"$ifNull": ["$amount", 0]}, 0]}},
                "total_adjustments": {"$sum": {"$cond": [{"$eq": ["$type", "adjustment"]}, {"$ifNull": ["$amount", 0]}, 0]}},
                "last_payment_date": {"$max": {"$cond": [{"$eq": ["$type", "payment"]}, "$created_at", None]}},
            }
        },
    ]
    plans_pipe = [
        {"$match": {"tenant_id": tenant_id, "agency_id": {"$in": aids}, "status": "active"}},
        {"$group": {"_id": "$agency_id", "active_plans": {"$sum": 1}}},
    ]

    bookings_agg, txns_agg, plans_agg = await _asyncio.gather(
        _db.bookings.aggregate(bookings_pipe).to_list(len(aids) + 10),
        _db.agency_transactions.aggregate(txns_pipe).to_list(len(aids) + 10),
        _db.agency_payment_plans.aggregate(plans_pipe).to_list(len(aids) + 10),
    )

    book_by: dict[str, dict[str, dict]] = {}
    for row in bookings_agg:
        group = row.get("_id") or {}
        book_by.setdefault(group.get("agency_id"), {})[_currency_code(group.get("currency"), tenant_currency)] = row
    txn_by: dict[str, dict[str, dict]] = {}
    for row in txns_agg:
        group = row.get("_id") or {}
        txn_by.setdefault(group.get("agency_id"), {})[_currency_code(group.get("currency"), tenant_currency)] = row
    plan_by = {row["_id"]: row for row in plans_agg}

    results = []
    now = datetime.now(UTC)
    for agency in agencies:
        aid = agency["id"]
        booking_currencies = book_by.get(aid, {})
        transaction_currencies = txn_by.get(aid, {})
        pl = plan_by.get(aid, {})

        commission_rate = agency.get("commission_rate", 10) / 100
        revenue_by_currency = {currency: float(row.get("total_revenue", 0) or 0) for currency, row in booking_currencies.items()}
        commission_by_currency = {currency: round(amount * commission_rate, 2) for currency, amount in revenue_by_currency.items()}
        paid_by_currency = {currency: float(row.get("total_paid", 0) or 0) for currency, row in transaction_currencies.items()}
        adjustments_by_currency = {currency: float(row.get("total_adjustments", 0) or 0) for currency, row in transaction_currencies.items()}
        balance_by_currency = {
            currency: round(
                commission_by_currency.get(currency, 0) - paid_by_currency.get(currency, 0) + adjustments_by_currency.get(currency, 0),
                2,
            )
            for currency in set(commission_by_currency) | set(paid_by_currency) | set(adjustments_by_currency)
        }

        oldest_candidates = [row.get("oldest_pending_created_at") for row in booking_currencies.values()]
        oldest_unpaid = _oldest_date(oldest_candidates)
        days_outstanding = 0
        if oldest_unpaid:
            try:
                if isinstance(oldest_unpaid, str):
                    od = datetime.fromisoformat(oldest_unpaid.replace("Z", "+00:00"))
                else:
                    od = oldest_unpaid
                if od.tzinfo is None:
                    od = od.replace(tzinfo=UTC)
                days_outstanding = (now - od).days
            except (ValueError, TypeError, AttributeError):
                pass

        active_plans_count = pl.get("active_plans", 0) or 0

        results.append(
            {
                "agency_id": aid,
                "agency_name": agency.get("name", ""),
                "contact_name": agency.get("contact_name", ""),
                "contact_email": agency.get("contact_email", ""),
                "contact_phone": agency.get("contact_phone", ""),
                "commission_rate": agency.get("commission_rate", 10),
                "status": agency.get("status", "active"),
                "currency": tenant_currency,
                "total_bookings": sum(int(row.get("count", 0) or 0) for row in booking_currencies.values()),
                "total_bookings_revenue": round(revenue_by_currency.get(tenant_currency, 0), 2),
                "total_bookings_revenue_by_currency": _round_currency_map(revenue_by_currency),
                "total_commission_owed": round(commission_by_currency.get(tenant_currency, 0), 2),
                "total_commission_owed_by_currency": _round_currency_map(commission_by_currency),
                "total_paid": round(paid_by_currency.get(tenant_currency, 0), 2),
                "total_paid_by_currency": _round_currency_map(paid_by_currency),
                "total_adjustments": round(adjustments_by_currency.get(tenant_currency, 0), 2),
                "total_adjustments_by_currency": _round_currency_map(adjustments_by_currency),
                "balance": round(balance_by_currency.get(tenant_currency, 0), 2),
                "balance_by_currency": _round_currency_map(balance_by_currency),
                "balance_type": "receivable" if balance_by_currency.get(tenant_currency, 0) >= 0 else "payable",
                "days_outstanding": days_outstanding,
                "oldest_unpaid_date": oldest_unpaid if isinstance(oldest_unpaid, str) else (oldest_unpaid.isoformat() if oldest_unpaid else None),
                "active_payment_plans": active_plans_count,
                "last_payment_date": max(
                    (value.isoformat() if hasattr(value, "isoformat") else value for value in (row.get("last_payment_date") for row in transaction_currencies.values()) if value),
                    default=None,
                ),
            }
        )

    return results


@router.get("/summary")
@cached(ttl=600, key_prefix="agent_arap_summary")  # heavy ledger aggregate (bulk-fetch + 10min cache)
async def get_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v80 Bug DP: agency A/R aging
):
    ledger = await _get_agency_ledger(current_user.tenant_id)
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    tenant_currency = _currency_code(tenant_currency)

    balance_totals = _sum_currency_maps(ledger, "balance_by_currency")
    total_receivable_by_currency = {currency: round(sum(max(float(a.get("balance_by_currency", {}).get(currency, 0)), 0) for a in ledger), 2) for currency in balance_totals}
    total_payable_by_currency = {currency: round(abs(sum(min(float(a.get("balance_by_currency", {}).get(currency, 0)), 0) for a in ledger)), 2) for currency in balance_totals}
    total_commission_by_currency = _sum_currency_maps(ledger, "total_commission_owed_by_currency")
    total_paid_by_currency = _sum_currency_maps(ledger, "total_paid_by_currency")
    total_bookings_revenue_by_currency = _sum_currency_maps(ledger, "total_bookings_revenue_by_currency")
    total_receivable = total_receivable_by_currency.get(tenant_currency, 0)
    total_payable = total_payable_by_currency.get(tenant_currency, 0)
    total_commission = total_commission_by_currency.get(tenant_currency, 0)
    total_paid = total_paid_by_currency.get(tenant_currency, 0)
    total_bookings_revenue = total_bookings_revenue_by_currency.get(tenant_currency, 0)

    def has_receivable(agency: dict) -> bool:
        return any(float(value or 0) > 0 for value in agency.get("balance_by_currency", {}).values())

    overdue_30 = sum(1 for a in ledger if a["days_outstanding"] > 30 and has_receivable(a))
    overdue_60 = sum(1 for a in ledger if a["days_outstanding"] > 60 and has_receivable(a))
    overdue_90 = sum(1 for a in ledger if a["days_outstanding"] > 90 and has_receivable(a))

    return {
        "total_agencies": len(ledger),
        "currency": tenant_currency,
        "total_receivable": round(total_receivable, 2),
        "total_receivable_by_currency": _round_currency_map(total_receivable_by_currency),
        "total_payable": round(total_payable, 2),
        "total_payable_by_currency": _round_currency_map(total_payable_by_currency),
        "net_balance": round(total_receivable - total_payable, 2),
        "net_balance_by_currency": _round_currency_map(balance_totals),
        "total_commission_earned": round(total_commission, 2),
        "total_commission_earned_by_currency": total_commission_by_currency,
        "total_paid": round(total_paid, 2),
        "total_paid_by_currency": total_paid_by_currency,
        "total_bookings_revenue": round(total_bookings_revenue, 2),
        "total_bookings_revenue_by_currency": total_bookings_revenue_by_currency,
        "collection_rate": round((total_paid / total_commission * 100), 1) if total_commission > 0 else 0,
        "overdue_30_count": overdue_30,
        "overdue_60_count": overdue_60,
        "overdue_90_count": overdue_90,
        "agencies": ledger,
    }


@router.get("/aging")
async def get_aging_report(current_user: User = Depends(get_current_user)):
    ledger = await _get_agency_ledger(current_user.tenant_id)
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    tenant_currency = _currency_code(tenant_currency)

    buckets = {"current": [], "30_days": [], "60_days": [], "90_days": [], "over_90": []}
    for a in ledger:
        if not any(float(value or 0) > 0 for value in a.get("balance_by_currency", {}).values()):
            continue
        d = a["days_outstanding"]
        if d <= 30:
            buckets["current"].append(a)
        elif d <= 60:
            buckets["30_days"].append(a)
        elif d <= 90:
            buckets["60_days"].append(a)
        elif d <= 120:
            buckets["90_days"].append(a)
        else:
            buckets["over_90"].append(a)

    response = {"currency": tenant_currency}
    for label, agencies in buckets.items():
        totals = _sum_currency_maps(agencies, "balance_by_currency")
        response[label] = {
            "count": len(agencies),
            "total": round(totals.get(tenant_currency, 0), 2),
            "totals_by_currency": totals,
            "agencies": [
                {
                    "agency_id": agency["agency_id"],
                    "agency_name": agency["agency_name"],
                    "balance": agency["balance"],
                    "balance_by_currency": agency.get("balance_by_currency", {}),
                }
                for agency in agencies
            ],
        }
    return response


@router.get("/chain/summary")
@cached(ttl=600, key_prefix="agent_arap_chain_summary", role_aware=True)
async def get_chain_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Konsolide acente cari özeti — kullanıcının zincirindeki TÜM otelleri
    tek görünümde toplar.

    - Süper-admin → tüm sistemdeki otellerin toplamı
    - Aynı `chain_id`'ye sahip oteller → kardeş tesislerin toplamı
    - chain_id yoksa → sadece kullanıcının kendi tesisi (tek-otel davranışı)

    Ödeme/komisyon hesabı her tesis için ayrı yapılır, sonuç toplanır.
    Her acente satırında `properties` alanı bulunur: hangi otel(ler)de
    ne kadar bakiye olduğunu gösterir.
    """
    tenant_ids = await _chain_tenant_ids(current_user)
    name_map = await _tenant_name_map(tenant_ids)

    # Chain bazlı: tenant-guarded `db` yerine `_sys_db` geç → cross-tenant
    # ledger okuma izinli (chain üyeliği zaten _chain_tenant_ids ile kontrol
    # edildi)
    import asyncio as _asyncio

    per_tenant_ledgers = await _asyncio.gather(*[_get_agency_ledger(tid, db_handle=_sys_db) for tid in tenant_ids])

    # Aynı acenteyi farklı tenant'larda birleştir.
    # Merge anahtarı önceliği (yüksek → düşük güven):
    #   1) normalized email (varsa)
    #   2) normalized phone (rakam dışı karakterler atılır)
    #   3) "name|tenant_id" — düşük güven; sadece aynı tenant içinde topla,
    #      farklı tenant'larda yanlış merge etmesin
    import re as _re

    by_agency_key: dict[str, dict] = {}
    property_breakdown: list[dict] = []

    def _merge_key(ag: dict, tid: str) -> str | None:
        email = (ag.get("contact_email") or "").strip().lower()
        if email:
            return f"email:{email}"
        phone_digits = _re.sub(r"\D+", "", ag.get("contact_phone") or "")
        if len(phone_digits) >= 7:
            return f"phone:{phone_digits}"
        name = (ag.get("agency_name") or "").strip().lower()
        if name:
            return f"local:{tid}:{name}"
        # son çare: agency_id (tenant içinde unique) — chain genelinde
        # asla başka tenant'la merge etmesin
        aid = ag.get("agency_id") or ""
        return f"local:{tid}:id:{aid}" if aid else None

    for tid, ledger in zip(tenant_ids, per_tenant_ledgers, strict=True):
        prop_name = name_map.get(tid, tid)
        prop_balance = _sum_currency_maps(ledger, "balance_by_currency")
        prop_recv = {currency: round(sum(max(float(a.get("balance_by_currency", {}).get(currency, 0)), 0) for a in ledger), 2) for currency in prop_balance}
        prop_pay = {currency: round(abs(sum(min(float(a.get("balance_by_currency", {}).get(currency, 0)), 0) for a in ledger)), 2) for currency in prop_balance}
        prop_commission = _sum_currency_maps(ledger, "total_commission_owed_by_currency")
        prop_paid = _sum_currency_maps(ledger, "total_paid_by_currency")
        prop_revenue = _sum_currency_maps(ledger, "total_bookings_revenue_by_currency")
        property_currencies = set(prop_balance) | set(prop_commission) | set(prop_paid) | set(prop_revenue)
        property_breakdown.append(
            {
                "tenant_id": tid,
                "property_name": prop_name,
                "agency_count": len(ledger),
                "mixed_currency": len(property_currencies) > 1,
                "total_receivable": _single_currency_amount(prop_recv),
                "total_receivable_by_currency": _round_currency_map(prop_recv),
                "total_payable": _single_currency_amount(prop_pay),
                "total_payable_by_currency": _round_currency_map(prop_pay),
                "total_commission_owed": _single_currency_amount(prop_commission),
                "total_commission_owed_by_currency": prop_commission,
                "total_paid": _single_currency_amount(prop_paid),
                "total_paid_by_currency": prop_paid,
                "total_bookings_revenue": _single_currency_amount(prop_revenue),
                "total_bookings_revenue_by_currency": prop_revenue,
            }
        )
        for ag in ledger:
            key = _merge_key(ag, tid)
            if not key:
                continue
            slot = by_agency_key.setdefault(
                key,
                {
                    "agency_name": ag.get("agency_name", ""),
                    "contact_email": ag.get("contact_email", ""),
                    "contact_phone": ag.get("contact_phone", ""),
                    "total_bookings": 0,
                    "total_bookings_revenue": 0.0,
                    "total_commission_owed": 0.0,
                    "total_paid": 0.0,
                    "total_adjustments": 0.0,
                    "balance": 0.0,
                    "total_bookings_revenue_by_currency": {},
                    "total_commission_owed_by_currency": {},
                    "total_paid_by_currency": {},
                    "total_adjustments_by_currency": {},
                    "balance_by_currency": {},
                    "max_days_outstanding": 0,
                    "properties": [],
                },
            )
            slot["total_bookings"] += ag["total_bookings"]
            slot["total_bookings_revenue"] += ag["total_bookings_revenue"]
            slot["total_commission_owed"] += ag["total_commission_owed"]
            slot["total_paid"] += ag["total_paid"]
            slot["total_adjustments"] += ag["total_adjustments"]
            slot["balance"] += ag["balance"]
            for field in (
                "total_bookings_revenue_by_currency",
                "total_commission_owed_by_currency",
                "total_paid_by_currency",
                "total_adjustments_by_currency",
                "balance_by_currency",
            ):
                for currency, amount in ag.get(field, {}).items():
                    _add_currency(slot[field], currency, amount)
            slot["max_days_outstanding"] = max(slot["max_days_outstanding"], ag.get("days_outstanding", 0))
            slot["properties"].append(
                {
                    "tenant_id": tid,
                    "property_name": prop_name,
                    "balance": ag["balance"],
                    "balance_by_currency": ag.get("balance_by_currency", {}),
                    "days_outstanding": ag.get("days_outstanding", 0),
                }
            )

    consolidated_agencies = []
    for slot in by_agency_key.values():
        slot["total_bookings_revenue"] = round(slot["total_bookings_revenue"], 2)
        slot["total_commission_owed"] = round(slot["total_commission_owed"], 2)
        slot["total_paid"] = round(slot["total_paid"], 2)
        slot["total_adjustments"] = round(slot["total_adjustments"], 2)
        for field in (
            "total_bookings_revenue_by_currency",
            "total_commission_owed_by_currency",
            "total_paid_by_currency",
            "total_adjustments_by_currency",
            "balance_by_currency",
        ):
            slot[field] = _round_currency_map(slot[field])
        slot["total_bookings_revenue"] = _single_currency_amount(slot["total_bookings_revenue_by_currency"])
        slot["total_commission_owed"] = _single_currency_amount(slot["total_commission_owed_by_currency"])
        slot["total_paid"] = _single_currency_amount(slot["total_paid_by_currency"])
        slot["total_adjustments"] = _single_currency_amount(slot["total_adjustments_by_currency"])
        slot["mixed_currency"] = len(slot["balance_by_currency"]) > 1
        slot["balance"] = _single_currency_amount(slot["balance_by_currency"])
        slot["balance_type"] = "receivable" if slot["balance"] >= 0 else "payable"
        consolidated_agencies.append(slot)

    consolidated_agencies.sort(
        key=lambda a: sum(max(float(value or 0), 0) for value in a["balance_by_currency"].values()),
        reverse=True,
    )

    balance_totals = _sum_currency_maps(consolidated_agencies, "balance_by_currency")
    total_receivable = {
        currency: round(
            sum(max(float(a.get("balance_by_currency", {}).get(currency, 0)), 0) for a in consolidated_agencies),
            2,
        )
        for currency in balance_totals
    }
    total_payable = {
        currency: round(
            abs(sum(min(float(a.get("balance_by_currency", {}).get(currency, 0)), 0) for a in consolidated_agencies)),
            2,
        )
        for currency in balance_totals
    }
    total_commission = _sum_currency_maps(consolidated_agencies, "total_commission_owed_by_currency")
    total_paid = _sum_currency_maps(consolidated_agencies, "total_paid_by_currency")
    total_revenue = _sum_currency_maps(consolidated_agencies, "total_bookings_revenue_by_currency")

    def _has_receivable(agency: dict) -> bool:
        return any(float(value or 0) > 0 for value in agency.get("balance_by_currency", {}).values())

    overdue_30 = sum(1 for a in consolidated_agencies if a["max_days_outstanding"] > 30 and _has_receivable(a))
    overdue_60 = sum(1 for a in consolidated_agencies if a["max_days_outstanding"] > 60 and _has_receivable(a))
    overdue_90 = sum(1 for a in consolidated_agencies if a["max_days_outstanding"] > 90 and _has_receivable(a))
    currencies = set(balance_totals) | set(total_commission) | set(total_paid) | set(total_revenue)
    collection_rates = {currency: round(total_paid.get(currency, 0) / commission * 100, 1) if commission > 0 else 0 for currency, commission in total_commission.items()}

    return {
        "scope": "chain" if len(tenant_ids) > 1 else "single_property",
        "total_properties": len(tenant_ids),
        "total_unique_agencies": len(consolidated_agencies),
        "mixed_currency": len(currencies) > 1,
        "total_receivable": _single_currency_amount(total_receivable),
        "total_receivable_by_currency": _round_currency_map(total_receivable),
        "total_payable": _single_currency_amount(total_payable),
        "total_payable_by_currency": _round_currency_map(total_payable),
        "net_balance": _single_currency_amount(balance_totals),
        "net_balance_by_currency": balance_totals,
        "total_commission_earned": _single_currency_amount(total_commission),
        "total_commission_earned_by_currency": total_commission,
        "total_paid": _single_currency_amount(total_paid),
        "total_paid_by_currency": total_paid,
        "total_bookings_revenue": _single_currency_amount(total_revenue),
        "total_bookings_revenue_by_currency": total_revenue,
        "collection_rate": _single_currency_amount(collection_rates),
        "collection_rate_by_currency": collection_rates,
        "overdue_30_count": overdue_30,
        "overdue_60_count": overdue_60,
        "overdue_90_count": overdue_90,
        "properties": property_breakdown,
        "agencies": consolidated_agencies,
    }


@router.get("/chain/aging")
@cached(ttl=600, key_prefix="agent_arap_chain_aging", role_aware=True)
async def get_chain_aging_report(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Zincir bazlı yaşlandırma raporu — chain'deki tüm otellerin
    açık alacaklarını yaş kovaları halinde toplar."""
    tenant_ids = await _chain_tenant_ids(current_user)
    name_map = await _tenant_name_map(tenant_ids)

    import asyncio as _asyncio

    per_tenant_ledgers = await _asyncio.gather(*[_get_agency_ledger(tid, db_handle=_sys_db) for tid in tenant_ids])

    buckets = {"current": [], "30_days": [], "60_days": [], "90_days": [], "over_90": []}
    for tid, ledger in zip(tenant_ids, per_tenant_ledgers, strict=True):
        prop_name = name_map.get(tid, tid)
        for a in ledger:
            positive_balances = {currency: float(amount or 0) for currency, amount in a.get("balance_by_currency", {}).items() if float(amount or 0) > 0}
            if not positive_balances:
                continue
            entry = {
                "agency_id": a["agency_id"],
                "agency_name": a["agency_name"],
                "balance": _single_currency_amount(positive_balances),
                "balance_by_currency": _round_currency_map(positive_balances),
                "mixed_currency": len(positive_balances) > 1,
                "tenant_id": tid,
                "property_name": prop_name,
                "days_outstanding": a["days_outstanding"],
            }
            d = a["days_outstanding"]
            if d <= 30:
                buckets["current"].append(entry)
            elif d <= 60:
                buckets["30_days"].append(entry)
            elif d <= 90:
                buckets["60_days"].append(entry)
            elif d <= 120:
                buckets["90_days"].append(entry)
            else:
                buckets["over_90"].append(entry)

    response = {
        "scope": "chain" if len(tenant_ids) > 1 else "single_property",
        "total_properties": len(tenant_ids),
    }
    for label, items in buckets.items():
        totals = _sum_currency_maps(items, "balance_by_currency")
        response[label] = {
            "count": len(items),
            "total": _single_currency_amount(totals),
            "totals_by_currency": totals,
            "mixed_currency": len(totals) > 1,
            "agencies": items,
        }
    return response


@router.get("/transactions/{agency_id}")
async def get_agency_transactions(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    agency = await db.agencies.find_one({"tenant_id": current_user.tenant_id, "id": agency_id})
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    tenant_currency = _currency_code(tenant_currency)

    txns = (
        await db.agency_transactions.find(
            {"tenant_id": current_user.tenant_id, "agency_id": agency_id},
        )
        .sort("created_at", -1)
        .to_list(500)
    )

    for t in txns:
        t.pop("_id", None)
        t["currency"] = _currency_code(t.get("currency"), tenant_currency)

    bookings = (
        await db.bookings.find(
            {"tenant_id": current_user.tenant_id, "agency_id": agency_id, "status": {"$nin": ["cancelled"]}},
            {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "check_out": 1, "total_amount": 1, "currency": 1, "status": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .to_list(500)
    )

    commission_rate = agency.get("commission_rate", 10) / 100
    commission_entries = []
    for b in bookings:
        commission_entries.append(
            {
                "id": f"comm-{b['id']}",
                "type": "commission",
                "booking_id": b["id"],
                "guest_name": b.get("guest_name", ""),
                "check_in": b.get("check_in", ""),
                "check_out": b.get("check_out", ""),
                "booking_amount": b.get("total_amount", 0),
                "amount": round(b.get("total_amount", 0) * commission_rate, 2),
                "currency": _currency_code(b.get("currency"), tenant_currency),
                "created_at": b.get("created_at", ""),
            }
        )

    return {
        "agency_id": agency_id,
        "agency_name": agency.get("name", ""),
        "commission_rate": agency.get("commission_rate", 10),
        "transactions": txns,
        "commission_entries": commission_entries,
    }


@router.post("/payment")
async def record_payment(
    req: RecordPaymentRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    agency = await db.agencies.find_one({"tenant_id": current_user.tenant_id, "id": req.agency_id})
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    currency = _currency_code(req.currency, tenant_currency)

    txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "agency_id": req.agency_id,
        "type": "payment",
        "amount": req.amount,
        "currency": currency,
        "payment_method": req.payment_method,
        "reference": req.reference,
        "notes": req.notes,
        "recorded_by": current_user.email,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.agency_transactions.insert_one(txn)
    txn.pop("_id", None)
    _invalidate_arap(current_user.tenant_id)
    return {"success": True, "transaction": txn}


@router.get("/payment-plans")
async def list_payment_plans(
    agency_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    tenant_currency = _currency_code(tenant_currency)
    match: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if agency_id:
        match["agency_id"] = agency_id

    plans = await db.agency_payment_plans.find(match).sort("created_at", -1).to_list(200)
    for p in plans:
        p.pop("_id", None)
        p["currency"] = _currency_code(p.get("currency"), tenant_currency)

    return plans


@router.post("/payment-plans")
async def create_payment_plan(
    req: CreatePaymentPlanRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    agency = await db.agencies.find_one({"tenant_id": current_user.tenant_id, "id": req.agency_id})
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")
    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    currency = _currency_code(req.currency, tenant_currency)

    try:
        start = datetime.fromisoformat(req.start_date)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid start_date format")

    installment_amount = round(req.total_amount / req.installments, 2)
    installments = []
    for i in range(req.installments):
        due_date = start + timedelta(days=30 * i)
        amount = installment_amount if i < req.installments - 1 else round(req.total_amount - installment_amount * (req.installments - 1), 2)
        installments.append(
            {
                "index": i,
                "due_date": due_date.strftime("%Y-%m-%d"),
                "amount": amount,
                "paid": False,
                "paid_date": None,
                "payment_reference": "",
            }
        )

    plan = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "agency_id": req.agency_id,
        "agency_name": agency.get("name", ""),
        "total_amount": req.total_amount,
        "currency": currency,
        "installment_count": req.installments,
        "installments": installments,
        "status": "active",
        "notes": req.notes,
        "created_by": current_user.email,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.agency_payment_plans.insert_one(plan)
    plan.pop("_id", None)
    _invalidate_arap(current_user.tenant_id)
    return {"success": True, "plan": plan}


@router.put("/payment-plans/installment")
async def update_installment(
    req: UpdatePaymentPlanInstallment,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    plan = await db.agency_payment_plans.find_one(
        {"tenant_id": current_user.tenant_id, "id": req.plan_id},
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Payment plan not found")

    installments = plan.get("installments", [])
    if req.installment_index >= len(installments):
        raise HTTPException(status_code=400, detail="Invalid installment index")

    was_already_paid = installments[req.installment_index].get("paid", False)

    if req.paid and was_already_paid:
        return {"success": True, "status": plan.get("status", "active"), "message": "Already paid"}

    installments[req.installment_index]["paid"] = req.paid
    installments[req.installment_index]["paid_date"] = datetime.now(UTC).strftime("%Y-%m-%d") if req.paid else None
    installments[req.installment_index]["payment_reference"] = req.payment_reference

    all_paid = all(inst["paid"] for inst in installments)
    new_status = "completed" if all_paid else "active"

    await db.agency_payment_plans.update_one(
        {"_id": plan["_id"]},
        {"$set": {"installments": installments, "status": new_status}},
    )

    if req.paid and not was_already_paid:
        tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
        txn = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "agency_id": plan["agency_id"],
            "type": "payment",
            "amount": installments[req.installment_index]["amount"],
            "currency": _currency_code(plan.get("currency"), tenant_currency),
            "payment_method": "payment_plan",
            "reference": req.payment_reference or f"Plan {req.plan_id[:8]} - Inst #{req.installment_index + 1}",
            "notes": f"Payment plan installment #{req.installment_index + 1}",
            "recorded_by": current_user.email,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.agency_transactions.insert_one(txn)

    _invalidate_arap(current_user.tenant_id)
    return {"success": True, "status": new_status}


@router.get("/statement/{agency_id}")
async def get_agency_statement(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    ledger = await _get_agency_ledger(current_user.tenant_id, agency_id)
    if not ledger:
        raise HTTPException(status_code=404, detail="Agency not found")

    agency_data = ledger[0]

    txns = (
        await db.agency_transactions.find(
            {"tenant_id": current_user.tenant_id, "agency_id": agency_id},
        )
        .sort("created_at", 1)
        .to_list(1000)
    )

    bookings = (
        await db.bookings.find(
            {"tenant_id": current_user.tenant_id, "agency_id": agency_id, "status": {"$nin": ["cancelled"]}},
            {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "check_out": 1, "total_amount": 1, "currency": 1, "created_at": 1},
        )
        .sort("created_at", 1)
        .to_list(1000)
    )

    commission_rate = agency_data["commission_rate"] / 100

    raw_lines = []

    for b in bookings:
        commission = round(b.get("total_amount", 0) * commission_rate, 2)
        raw_lines.append(
            {
                "date": b.get("created_at", "")[:10],
                "sort_key": b.get("created_at", ""),
                "description": f"Commission: {b.get('guest_name', 'Guest')} ({b.get('check_in', '')} - {b.get('check_out', '')})",
                "debit": commission,
                "credit": 0,
                "currency": _currency_code(b.get("currency"), agency_data.get("currency", "TRY")),
                "type": "commission",
                "booking_id": b.get("id", ""),
            }
        )

    for t in txns:
        t.pop("_id", None)
        if t.get("type") == "payment":
            raw_lines.append(
                {
                    "date": t.get("created_at", "")[:10],
                    "sort_key": t.get("created_at", ""),
                    "description": f"Payment: {t.get('payment_method', '')} - {t.get('reference', '')}",
                    "debit": 0,
                    "credit": t.get("amount", 0),
                    "currency": _currency_code(t.get("currency"), agency_data.get("currency", "TRY")),
                    "type": "payment",
                    "reference": t.get("reference", ""),
                }
            )
        elif t.get("type") == "adjustment":
            raw_lines.append(
                {
                    "date": t.get("created_at", "")[:10],
                    "sort_key": t.get("created_at", ""),
                    "description": f"Adjustment: {t.get('notes', '')}",
                    "debit": t.get("amount", 0) if t.get("amount", 0) > 0 else 0,
                    "credit": abs(t.get("amount", 0)) if t.get("amount", 0) < 0 else 0,
                    "currency": _currency_code(t.get("currency"), agency_data.get("currency", "TRY")),
                    "type": "adjustment",
                }
            )

    raw_lines.sort(key=lambda x: x.get("sort_key", ""))

    statement_lines = []
    running_balances: dict[str, float] = {}
    for line in raw_lines:
        currency = _currency_code(line.get("currency"), agency_data.get("currency", "TRY"))
        running_balances[currency] = running_balances.get(currency, 0) + line.get("debit", 0) - line.get("credit", 0)
        line["balance"] = round(running_balances[currency], 2)
        line.pop("sort_key", None)
        statement_lines.append(line)

    return {
        **agency_data,
        "statement": statement_lines,
    }
