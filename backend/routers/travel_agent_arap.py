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


class RecordPaymentRequest(BaseModel):
    agency_id: str
    amount: float = Field(..., gt=0)
    payment_method: str = "bank_transfer"
    reference: str = ""
    notes: str = ""


class CreatePaymentPlanRequest(BaseModel):
    agency_id: str
    total_amount: float = Field(..., gt=0)
    installments: int = Field(..., ge=2, le=24)
    start_date: str
    notes: str = ""


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
        {"$match": {"tenant_id": tenant_id, "agency_id": {"$in": aids},
                    "status": {"$nin": ["cancelled"]}}},
        {"$group": {
            "_id": "$agency_id",
            "total_revenue": {"$sum": {"$ifNull": ["$total_amount", 0]}},
            "count": {"$sum": 1},
            # Oldest unpaid: bekleyen status'lardaki en eski created_at
            "oldest_pending_created_at": {"$min": {
                "$cond": [
                    {"$in": ["$status", ["confirmed", "guaranteed", "checked_out"]]},
                    "$created_at", None,
                ]
            }},
        }},
    ]
    txns_pipe = [
        {"$match": {"tenant_id": tenant_id, "agency_id": {"$in": aids}}},
        {"$group": {
            "_id": "$agency_id",
            "total_paid": {"$sum": {"$cond": [
                {"$eq": ["$type", "payment"]},
                {"$ifNull": ["$amount", 0]}, 0]}},
            "total_adjustments": {"$sum": {"$cond": [
                {"$eq": ["$type", "adjustment"]},
                {"$ifNull": ["$amount", 0]}, 0]}},
            "last_payment_date": {"$max": {"$cond": [
                {"$eq": ["$type", "payment"]}, "$created_at", None]}},
        }},
    ]
    plans_pipe = [
        {"$match": {"tenant_id": tenant_id, "agency_id": {"$in": aids},
                    "status": "active"}},
        {"$group": {"_id": "$agency_id", "active_plans": {"$sum": 1}}},
    ]

    bookings_agg, txns_agg, plans_agg = await _asyncio.gather(
        _db.bookings.aggregate(bookings_pipe).to_list(len(aids) + 10),
        _db.agency_transactions.aggregate(txns_pipe).to_list(len(aids) + 10),
        _db.agency_payment_plans.aggregate(plans_pipe).to_list(len(aids) + 10),
    )

    book_by = {row["_id"]: row for row in bookings_agg}
    txn_by = {row["_id"]: row for row in txns_agg}
    plan_by = {row["_id"]: row for row in plans_agg}

    results = []
    now = datetime.now(UTC)
    for agency in agencies:
        aid = agency["id"]
        bk = book_by.get(aid, {})
        tx = txn_by.get(aid, {})
        pl = plan_by.get(aid, {})

        total_bookings_revenue = bk.get("total_revenue", 0) or 0
        commission_rate = agency.get("commission_rate", 10) / 100
        total_commission_owed = round(total_bookings_revenue * commission_rate, 2)

        total_paid = tx.get("total_paid", 0) or 0
        total_adjustments = tx.get("total_adjustments", 0) or 0
        balance = round(total_commission_owed - total_paid + total_adjustments, 2)

        oldest_unpaid = bk.get("oldest_pending_created_at")
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

        results.append({
            "agency_id": aid,
            "agency_name": agency.get("name", ""),
            "contact_name": agency.get("contact_name", ""),
            "contact_email": agency.get("contact_email", ""),
            "contact_phone": agency.get("contact_phone", ""),
            "commission_rate": agency.get("commission_rate", 10),
            "status": agency.get("status", "active"),
            "total_bookings": bk.get("count", 0) or 0,
            "total_bookings_revenue": total_bookings_revenue,
            "total_commission_owed": total_commission_owed,
            "total_paid": round(total_paid, 2),
            "total_adjustments": round(total_adjustments, 2),
            "balance": balance,
            "balance_type": "receivable" if balance >= 0 else "payable",
            "days_outstanding": days_outstanding,
            "oldest_unpaid_date": oldest_unpaid if isinstance(oldest_unpaid, str)
                else (oldest_unpaid.isoformat() if oldest_unpaid else None),
            "active_payment_plans": active_plans_count,
            "last_payment_date": (
                tx.get("last_payment_date").isoformat()
                if hasattr(tx.get("last_payment_date"), "isoformat")
                else tx.get("last_payment_date")
            ),
        })

    return results


@router.get("/summary")
@cached(ttl=600, key_prefix="agent_arap_summary")  # heavy ledger aggregate (bulk-fetch + 10min cache)
async def get_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v80 Bug DP: agency A/R aging
):
    ledger = await _get_agency_ledger(current_user.tenant_id)

    total_receivable = sum(a["balance"] for a in ledger if a["balance"] > 0)
    total_payable = abs(sum(a["balance"] for a in ledger if a["balance"] < 0))
    total_commission = sum(a["total_commission_owed"] for a in ledger)
    total_paid = sum(a["total_paid"] for a in ledger)
    total_bookings_revenue = sum(a["total_bookings_revenue"] for a in ledger)

    overdue_30 = sum(1 for a in ledger if a["days_outstanding"] > 30 and a["balance"] > 0)
    overdue_60 = sum(1 for a in ledger if a["days_outstanding"] > 60 and a["balance"] > 0)
    overdue_90 = sum(1 for a in ledger if a["days_outstanding"] > 90 and a["balance"] > 0)

    return {
        "total_agencies": len(ledger),
        "total_receivable": round(total_receivable, 2),
        "total_payable": round(total_payable, 2),
        "net_balance": round(total_receivable - total_payable, 2),
        "total_commission_earned": round(total_commission, 2),
        "total_paid": round(total_paid, 2),
        "total_bookings_revenue": round(total_bookings_revenue, 2),
        "collection_rate": round((total_paid / total_commission * 100), 1) if total_commission > 0 else 0,
        "overdue_30_count": overdue_30,
        "overdue_60_count": overdue_60,
        "overdue_90_count": overdue_90,
        "agencies": ledger,
    }


@router.get("/aging")
async def get_aging_report(current_user: User = Depends(get_current_user)):
    ledger = await _get_agency_ledger(current_user.tenant_id)

    buckets = {"current": [], "30_days": [], "60_days": [], "90_days": [], "over_90": []}
    for a in ledger:
        if a["balance"] <= 0:
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

    return {
        "current": {
            "count": len(buckets["current"]),
            "total": round(sum(a["balance"] for a in buckets["current"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["current"]],
        },
        "30_days": {
            "count": len(buckets["30_days"]),
            "total": round(sum(a["balance"] for a in buckets["30_days"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["30_days"]],
        },
        "60_days": {
            "count": len(buckets["60_days"]),
            "total": round(sum(a["balance"] for a in buckets["60_days"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["60_days"]],
        },
        "90_days": {
            "count": len(buckets["90_days"]),
            "total": round(sum(a["balance"] for a in buckets["90_days"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["90_days"]],
        },
        "over_90": {
            "count": len(buckets["over_90"]),
            "total": round(sum(a["balance"] for a in buckets["over_90"]), 2),
            "agencies": [{"agency_id": a["agency_id"], "agency_name": a["agency_name"], "balance": a["balance"]} for a in buckets["over_90"]],
        },
    }


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
    per_tenant_ledgers = await _asyncio.gather(
        *[_get_agency_ledger(tid, db_handle=_sys_db) for tid in tenant_ids]
    )

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
        prop_recv = sum(a["balance"] for a in ledger if a["balance"] > 0)
        prop_pay = abs(sum(a["balance"] for a in ledger if a["balance"] < 0))
        property_breakdown.append({
            "tenant_id": tid,
            "property_name": prop_name,
            "agency_count": len(ledger),
            "total_receivable": round(prop_recv, 2),
            "total_payable": round(prop_pay, 2),
            "total_commission_owed": round(sum(a["total_commission_owed"] for a in ledger), 2),
            "total_paid": round(sum(a["total_paid"] for a in ledger), 2),
            "total_bookings_revenue": round(sum(a["total_bookings_revenue"] for a in ledger), 2),
        })
        for ag in ledger:
            key = _merge_key(ag, tid)
            if not key:
                continue
            slot = by_agency_key.setdefault(key, {
                "agency_name": ag.get("agency_name", ""),
                "contact_email": ag.get("contact_email", ""),
                "contact_phone": ag.get("contact_phone", ""),
                "total_bookings": 0,
                "total_bookings_revenue": 0.0,
                "total_commission_owed": 0.0,
                "total_paid": 0.0,
                "total_adjustments": 0.0,
                "balance": 0.0,
                "max_days_outstanding": 0,
                "properties": [],
            })
            slot["total_bookings"] += ag["total_bookings"]
            slot["total_bookings_revenue"] += ag["total_bookings_revenue"]
            slot["total_commission_owed"] += ag["total_commission_owed"]
            slot["total_paid"] += ag["total_paid"]
            slot["total_adjustments"] += ag["total_adjustments"]
            slot["balance"] += ag["balance"]
            slot["max_days_outstanding"] = max(
                slot["max_days_outstanding"], ag.get("days_outstanding", 0)
            )
            slot["properties"].append({
                "tenant_id": tid,
                "property_name": prop_name,
                "balance": ag["balance"],
                "days_outstanding": ag.get("days_outstanding", 0),
            })

    consolidated_agencies = []
    for slot in by_agency_key.values():
        slot["total_bookings_revenue"] = round(slot["total_bookings_revenue"], 2)
        slot["total_commission_owed"] = round(slot["total_commission_owed"], 2)
        slot["total_paid"] = round(slot["total_paid"], 2)
        slot["total_adjustments"] = round(slot["total_adjustments"], 2)
        slot["balance"] = round(slot["balance"], 2)
        slot["balance_type"] = "receivable" if slot["balance"] >= 0 else "payable"
        consolidated_agencies.append(slot)

    consolidated_agencies.sort(key=lambda a: a["balance"], reverse=True)

    total_receivable = sum(a["balance"] for a in consolidated_agencies if a["balance"] > 0)
    total_payable = abs(sum(a["balance"] for a in consolidated_agencies if a["balance"] < 0))
    total_commission = sum(a["total_commission_owed"] for a in consolidated_agencies)
    total_paid = sum(a["total_paid"] for a in consolidated_agencies)
    total_revenue = sum(a["total_bookings_revenue"] for a in consolidated_agencies)

    overdue_30 = sum(1 for a in consolidated_agencies
                     if a["max_days_outstanding"] > 30 and a["balance"] > 0)
    overdue_60 = sum(1 for a in consolidated_agencies
                     if a["max_days_outstanding"] > 60 and a["balance"] > 0)
    overdue_90 = sum(1 for a in consolidated_agencies
                     if a["max_days_outstanding"] > 90 and a["balance"] > 0)

    return {
        "scope": "chain" if len(tenant_ids) > 1 else "single_property",
        "total_properties": len(tenant_ids),
        "total_unique_agencies": len(consolidated_agencies),
        "total_receivable": round(total_receivable, 2),
        "total_payable": round(total_payable, 2),
        "net_balance": round(total_receivable - total_payable, 2),
        "total_commission_earned": round(total_commission, 2),
        "total_paid": round(total_paid, 2),
        "total_bookings_revenue": round(total_revenue, 2),
        "collection_rate": round((total_paid / total_commission * 100), 1)
            if total_commission > 0 else 0,
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
    per_tenant_ledgers = await _asyncio.gather(
        *[_get_agency_ledger(tid, db_handle=_sys_db) for tid in tenant_ids]
    )

    buckets = {"current": [], "30_days": [], "60_days": [], "90_days": [], "over_90": []}
    for tid, ledger in zip(tenant_ids, per_tenant_ledgers, strict=True):
        prop_name = name_map.get(tid, tid)
        for a in ledger:
            if a["balance"] <= 0:
                continue
            entry = {
                "agency_id": a["agency_id"],
                "agency_name": a["agency_name"],
                "balance": a["balance"],
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

    return {
        "scope": "chain" if len(tenant_ids) > 1 else "single_property",
        "total_properties": len(tenant_ids),
        **{
            label: {
                "count": len(items),
                "total": round(sum(x["balance"] for x in items), 2),
                "agencies": items,
            }
            for label, items in buckets.items()
        },
    }


@router.get("/transactions/{agency_id}")
async def get_agency_transactions(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    agency = await db.agencies.find_one({"tenant_id": current_user.tenant_id, "id": agency_id})
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")

    txns = await db.agency_transactions.find(
        {"tenant_id": current_user.tenant_id, "agency_id": agency_id},
    ).sort("created_at", -1).to_list(500)

    for t in txns:
        t.pop("_id", None)

    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "agency_id": agency_id, "status": {"$nin": ["cancelled"]}},
        {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "check_out": 1, "total_amount": 1, "status": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(500)

    commission_rate = agency.get("commission_rate", 10) / 100
    commission_entries = []
    for b in bookings:
        commission_entries.append({
            "id": f"comm-{b['id']}",
            "type": "commission",
            "booking_id": b["id"],
            "guest_name": b.get("guest_name", ""),
            "check_in": b.get("check_in", ""),
            "check_out": b.get("check_out", ""),
            "booking_amount": b.get("total_amount", 0),
            "amount": round(b.get("total_amount", 0) * commission_rate, 2),
            "created_at": b.get("created_at", ""),
        })

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

    txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "agency_id": req.agency_id,
        "type": "payment",
        "amount": req.amount,
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
    match: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if agency_id:
        match["agency_id"] = agency_id

    plans = await db.agency_payment_plans.find(match).sort("created_at", -1).to_list(200)
    for p in plans:
        p.pop("_id", None)

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

    try:
        start = datetime.fromisoformat(req.start_date)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid start_date format")

    installment_amount = round(req.total_amount / req.installments, 2)
    installments = []
    for i in range(req.installments):
        due_date = start + timedelta(days=30 * i)
        amount = installment_amount if i < req.installments - 1 else round(req.total_amount - installment_amount * (req.installments - 1), 2)
        installments.append({
            "index": i,
            "due_date": due_date.strftime("%Y-%m-%d"),
            "amount": amount,
            "paid": False,
            "paid_date": None,
            "payment_reference": "",
        })

    plan = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "agency_id": req.agency_id,
        "agency_name": agency.get("name", ""),
        "total_amount": req.total_amount,
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
        txn = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "agency_id": plan["agency_id"],
            "type": "payment",
            "amount": installments[req.installment_index]["amount"],
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

    txns = await db.agency_transactions.find(
        {"tenant_id": current_user.tenant_id, "agency_id": agency_id},
    ).sort("created_at", 1).to_list(1000)

    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "agency_id": agency_id, "status": {"$nin": ["cancelled"]}},
        {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "check_out": 1, "total_amount": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(1000)

    commission_rate = agency_data["commission_rate"] / 100

    raw_lines = []

    for b in bookings:
        commission = round(b.get("total_amount", 0) * commission_rate, 2)
        raw_lines.append({
            "date": b.get("created_at", "")[:10],
            "sort_key": b.get("created_at", ""),
            "description": f"Commission: {b.get('guest_name', 'Guest')} ({b.get('check_in', '')} - {b.get('check_out', '')})",
            "debit": commission,
            "credit": 0,
            "type": "commission",
            "booking_id": b.get("id", ""),
        })

    for t in txns:
        t.pop("_id", None)
        if t.get("type") == "payment":
            raw_lines.append({
                "date": t.get("created_at", "")[:10],
                "sort_key": t.get("created_at", ""),
                "description": f"Payment: {t.get('payment_method', '')} - {t.get('reference', '')}",
                "debit": 0,
                "credit": t.get("amount", 0),
                "type": "payment",
                "reference": t.get("reference", ""),
            })
        elif t.get("type") == "adjustment":
            raw_lines.append({
                "date": t.get("created_at", "")[:10],
                "sort_key": t.get("created_at", ""),
                "description": f"Adjustment: {t.get('notes', '')}",
                "debit": t.get("amount", 0) if t.get("amount", 0) > 0 else 0,
                "credit": abs(t.get("amount", 0)) if t.get("amount", 0) < 0 else 0,
                "type": "adjustment",
            })

    raw_lines.sort(key=lambda x: x.get("sort_key", ""))

    statement_lines = []
    running_balance = 0
    for line in raw_lines:
        running_balance += line.get("debit", 0) - line.get("credit", 0)
        line["balance"] = round(running_balance, 2)
        line.pop("sort_key", None)
        statement_lines.append(line)

    return {
        **agency_data,
        "statement": statement_lines,
    }
