"""Marketplace v2 — Acente ↔ Otel Sözleşmeleri.

Marketplace artık "açık pazaryeri" değil, **anlaşma-tabanlı B2B platform**:
acente bir otele teklif gönderir, otel onaylarsa o acente o otele
arama/rezervasyon yapabilir.

İki taraflı API:
  • Acente tarafı (X-API-Key, /api/marketplace/v1/contracts/*):
      - propose, mine, get, withdraw
  • Otelci tarafı (PMS JWT, /api/marketplace/incoming-requests/*):
      - list (pending/active/history), get, approve, reject, terminate

Diğer modüller (marketplace_b2b.py) `has_active_contract()` helper'ını
kullanarak arama/rezervasyon akışlarını gate eder.
"""

from __future__ import annotations
from modules.pms_core.role_permission_service import require_op  # v95 DW

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.security import get_current_user
from core.tenant_db import get_system_db, tenant_context  # noqa: F401
from models.schemas import User

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# ─── Index management (race-condition koruması + perf) ─────────────────────

_indexes_ready = False


async def _ensure_indexes() -> None:
    """İlk istekte (lazy) gerekli indeksleri yarat. Idempotent."""
    global _indexes_ready
    if _indexes_ready:
        return
    sysdb = get_system_db()
    coll = sysdb.agency_contracts

    # 1) Tek aktif sözleşme zorunluluğu — partial unique
    await coll.create_index(
        [("agency_id", 1), ("tenant_id", 1)],
        unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "approved"]}},
        name="uniq_active_contract",
    )
    # 2) ID & contract_code unique
    await coll.create_index([("id", 1)], unique=True, name="uniq_id")
    await coll.create_index([("contract_code", 1)], unique=True, name="uniq_code")
    # 3) Perf: tek otel kontrolü (has_active_contract)
    await coll.create_index(
        [("agency_id", 1), ("tenant_id", 1), ("status", 1),
         ("valid_from", 1), ("valid_to", 1)],
        name="perf_active_lookup",
    )
    # 4) Perf: partner listeleme
    await coll.create_index(
        [("agency_id", 1), ("status", 1), ("valid_from", 1), ("valid_to", 1)],
        name="perf_partners",
    )
    _indexes_ready = True


# ─── Public helper (marketplace_b2b.py'den çağrılır) ──────────────────────

async def has_active_contract(agency_id: str, tenant_id: str, on_date: str | None = None) -> dict | None:
    """O acentenin o otelle on_date için aktif (approved + tarih içinde) sözleşmesi
    var mı? Varsa sözleşme dict'i, yoksa None döner.
    """
    sysdb = get_system_db()
    today = on_date or datetime.now(UTC).strftime("%Y-%m-%d")
    contract = await sysdb.agency_contracts.find_one(
        {
            "agency_id": agency_id,
            "tenant_id": tenant_id,
            "status": "approved",
            "valid_from": {"$lte": today},
            "valid_to": {"$gte": today},
        },
        {"_id": 0},
    )
    return contract


async def list_partner_tenant_ids(agency_id: str, on_date: str | None = None) -> list[str]:
    """Bu acentenin bugün aktif sözleşmesi olan tüm tenant_id listesi."""
    sysdb = get_system_db()
    today = on_date or datetime.now(UTC).strftime("%Y-%m-%d")
    cursor = sysdb.agency_contracts.find(
        {
            "agency_id": agency_id,
            "status": "approved",
            "valid_from": {"$lte": today},
            "valid_to": {"$gte": today},
        },
        {"_id": 0, "tenant_id": 1},
    )
    return [doc["tenant_id"] async for doc in cursor]


# ═══════════════════════════════════════════════════════════════════════
# AGENCY-SIDE (X-API-Key)
# ═══════════════════════════════════════════════════════════════════════

agency_router = APIRouter(prefix="/api/marketplace/v1", tags=["Marketplace v1 / Contracts"])


class CancellationPolicy(BaseModel):
    free_until_days_before: int = Field(default=7, ge=0, le=365)
    penalty_pct: float = Field(default=50.0, ge=0, le=100)
    no_show_penalty_pct: float = Field(default=100.0, ge=0, le=100)


class ContractPropose(BaseModel):
    tenant_id: str
    commission_pct: float = Field(default=12.0, ge=0, le=100)
    cancellation_policy: CancellationPolicy = Field(default_factory=CancellationPolicy)
    payment_terms: str = Field(default="on_arrival",
                               pattern="^(prepaid|on_arrival|net_7|net_15|net_30)$")
    valid_from: str  # YYYY-MM-DD
    valid_to: str    # YYYY-MM-DD
    currency: str = Field(default="TRY", pattern="^[A-Z]{3}$")
    allowed_room_types: list[str] = []
    special_terms: str = ""


def _validate_dates(valid_from: str, valid_to: str) -> None:
    try:
        vf = datetime.fromisoformat(valid_from)
        vt = datetime.fromisoformat(valid_to)
    except (ValueError, TypeError):
        raise HTTPException(400, "Geçersiz tarih (YYYY-MM-DD)")
    if vt <= vf:
        raise HTTPException(400, "valid_to, valid_from'dan sonra olmalı")
    if (vt - vf) > timedelta(days=730):
        raise HTTPException(400, "Sözleşme süresi en fazla 2 yıl olabilir")


async def _get_agency_dep():
    """Lazy import — marketplace_b2b.get_marketplace_agency'yi tekrar kullanırız."""
    from routers.marketplace_b2b import get_marketplace_agency
    return get_marketplace_agency


# Bağımlılık zincirini başlangıçta çözelim (FastAPI Depends için)
from routers.marketplace_b2b import (  # noqa: E402
    _get_listing_or_404 as _listing_dep,
)
from routers.marketplace_b2b import (
    get_marketplace_agency as _agency_dep,
)


async def _next_contract_code(sysdb) -> str:
    """Atomik counter — yarışa açık değil."""
    year = datetime.now(UTC).year
    counter = await sysdb.counters.find_one_and_update(
        {"_id": f"contract_code_{year}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"SOZ-{year}-{counter['seq']:04d}"


@agency_router.post("/contracts/propose")
async def contract_propose(
    data: ContractPropose,
    agency: dict = Depends(_agency_dep),
):
    """Yeni sözleşme teklifi (acente → otel)."""
    _validate_dates(data.valid_from, data.valid_to)
    listing = await _listing_dep(data.tenant_id)

    sysdb = get_system_db()
    await _ensure_indexes()

    contract_id = _uuid()
    contract_code = await _next_contract_code(sysdb)
    doc = {
        "id": contract_id,
        "contract_code": contract_code,
        "agency_id": agency["agency_id"],
        "agency_name": agency["agency_name"],
        "agency_country": agency.get("country", ""),
        "agency_email": agency.get("contact_email", ""),
        "tenant_id": data.tenant_id,
        "hotel_name": listing.get("hotel_name", ""),
        "hotel_city": listing.get("city", ""),
        "status": "pending",
        "commission_pct": data.commission_pct,
        "agency_proposed_commission_pct": data.commission_pct,
        "cancellation_policy": data.cancellation_policy.model_dump(),
        "payment_terms": data.payment_terms,
        "valid_from": data.valid_from,
        "valid_to": data.valid_to,
        "currency": data.currency,
        "allowed_room_types": data.allowed_room_types,
        "special_terms": data.special_terms,
        "proposed_at": _now_iso(),
        "proposed_by_email": agency.get("contact_email", ""),
        "decided_at": None,
        "decided_by": None,
        "decision_notes": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        await sysdb.agency_contracts.insert_one(doc)
    except DuplicateKeyError:
        # Partial unique index tetiklendi → zaten pending/approved bir sözleşme var
        existing = await sysdb.agency_contracts.find_one({
            "agency_id": agency["agency_id"],
            "tenant_id": data.tenant_id,
            "status": {"$in": ["pending", "approved"]},
        }, {"_id": 0, "id": 1, "status": 1, "contract_code": 1})
        raise HTTPException(
            409,
            f"Bu otelle zaten {existing['status']} durumda bir sözleşmeniz var "
            f"({existing['contract_code']}). Önce onu sonlandırın/geri çekin."
        )
    doc.pop("_id", None)
    return {"ok": True, "contract": doc}


async def _list_agency_contracts(status: str | None, limit: int, agency: dict) -> dict:
    sysdb = get_system_db()
    q: dict = {"agency_id": agency["agency_id"]}
    if status:
        q["status"] = status
    docs = await sysdb.agency_contracts.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"contracts": docs, "total": len(docs)}


@agency_router.get("/contracts/mine")
async def contract_list_mine(
    status: str | None = Query(None, pattern="^(pending|approved|rejected|terminated|expired|withdrawn)$"),
    limit: int = Query(100, le=500),
    agency: dict = Depends(_agency_dep),
):
    return await _list_agency_contracts(status, limit, agency)


# Alias — Acente otomasyon SaaS'ı GET /contracts/ kullanıyor
@agency_router.get("/contracts")
@agency_router.get("/contracts/")
async def contract_list_root(
    status: str | None = Query(None, pattern="^(pending|approved|rejected|terminated|expired|withdrawn)$"),
    limit: int = Query(100, le=500),
    agency: dict = Depends(_agency_dep),
):
    return await _list_agency_contracts(status, limit, agency)


@agency_router.get("/contracts/{contract_id}")
async def contract_get(
    contract_id: str,
    agency: dict = Depends(_agency_dep),
):
    sysdb = get_system_db()
    doc = await sysdb.agency_contracts.find_one(
        {"id": contract_id, "agency_id": agency["agency_id"]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(404, "Sözleşme bulunamadı")
    return {"contract": doc}


@agency_router.delete("/contracts/{contract_id}")
async def contract_withdraw(
    contract_id: str,
    agency: dict = Depends(_agency_dep),
):
    """Acente kendi pending teklifini geri çekebilir."""
    sysdb = get_system_db()
    contract = await sysdb.agency_contracts.find_one_and_update(
        {"id": contract_id, "agency_id": agency["agency_id"], "status": "pending"},
        {"$set": {"status": "withdrawn", "updated_at": _now_iso(),
                  "decision_notes": "Acente tarafından geri çekildi"}},
        projection={"_id": 0, "id": 1, "status": 1},
        return_document=ReturnDocument.AFTER,
    )
    if not contract:
        any_doc = await sysdb.agency_contracts.find_one(
            {"id": contract_id, "agency_id": agency["agency_id"]}, {"_id": 0, "status": 1}
        )
        if not any_doc:
            raise HTTPException(404, "Sözleşme bulunamadı")
        raise HTTPException(409, "Sadece bekleyen teklifler geri çekilebilir")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════
# HOTEL-SIDE (PMS JWT) — Gelen Acente Talepleri
# ═══════════════════════════════════════════════════════════════════════

hotel_router = APIRouter(prefix="/api/marketplace/incoming-requests", tags=["Marketplace v1 / Incoming"])


def _require_hotel_user(user: User) -> str:
    if user.role in ("agency_admin", "agency_agent"):
        raise HTTPException(403, "Acente kullanıcısı bu sayfayı görüntüleyemez")
    if not user.tenant_id:
        raise HTTPException(403, "Geçerli bir otel kiracısı yok")
    return user.tenant_id


class ApproveRequest(BaseModel):
    commission_pct_override: float | None = Field(default=None, ge=0, le=100)
    notes: str = ""


class RejectRequest(BaseModel):
    reason: str = ""


class TerminateRequest(BaseModel):
    reason: str = ""
    effective_date: str | None = None  # YYYY-MM-DD; None ise hemen


@hotel_router.get("")
async def hotel_list_requests(
    status: str | None = Query(None, pattern="^(pending|approved|rejected|terminated|expired|withdrawn)$"),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _require_hotel_user(current_user)
    sysdb = get_system_db()
    q: dict = {"tenant_id": tenant_id}
    if status:
        q["status"] = status
    docs = await sysdb.agency_contracts.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

    # Sayaçlar (UI rozeti için)
    counts = {"pending": 0, "approved": 0, "rejected": 0,
              "terminated": 0, "expired": 0, "withdrawn": 0}
    async for doc in sysdb.agency_contracts.find(
        {"tenant_id": tenant_id}, {"_id": 0, "status": 1}
    ):
        s = doc.get("status", "pending")
        counts[s] = counts.get(s, 0) + 1

    return {"contracts": docs, "total": len(docs), "counts": counts}


@hotel_router.get("/{contract_id}")
async def hotel_get_request(
    contract_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = _require_hotel_user(current_user)
    sysdb = get_system_db()
    doc = await sysdb.agency_contracts.find_one(
        {"id": contract_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(404, "Sözleşme bulunamadı")
    return {"contract": doc}


@hotel_router.post("/{contract_id}/approve")
async def hotel_approve_request(
    contract_id: str,
    data: ApproveRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    tenant_id = _require_hotel_user(current_user)
    sysdb = get_system_db()

    # Önce mevcut komisyonu öğren (override yoksa korumak için)
    existing = await sysdb.agency_contracts.find_one(
        {"id": contract_id, "tenant_id": tenant_id},
        {"_id": 0, "commission_pct": 1, "status": 1}
    )
    if not existing:
        raise HTTPException(404, "Sözleşme bulunamadı")
    if existing["status"] != "pending":
        raise HTTPException(409, f"Bu sözleşme zaten '{existing['status']}' durumunda")

    final_pct = (
        data.commission_pct_override
        if data.commission_pct_override is not None
        else existing["commission_pct"]
    )
    # ATOMIC: yalnızca status="pending" iken güncelle. Başka istek araya girip
    # durumu değiştirdiyse update düşmez.
    contract = await sysdb.agency_contracts.find_one_and_update(
        {"id": contract_id, "tenant_id": tenant_id, "status": "pending"},
        {"$set": {
            "status": "approved",
            "commission_pct": final_pct,
            "hotel_approved_commission_pct": final_pct,
            "decided_at": _now_iso(),
            "decided_by": current_user.email,
            "decision_notes": data.notes,
            "updated_at": _now_iso(),
        }},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not contract:
        raise HTTPException(409, "Sözleşme durumu eş zamanlı bir istekle değişti, lütfen yenileyin")

    await sysdb.agency_contract_events.insert_one({
        "id": _uuid(),
        "contract_id": contract_id,
        "agency_id": contract["agency_id"],
        "tenant_id": tenant_id,
        "event": "approved",
        "actor": current_user.email,
        "payload": {"commission_pct": final_pct, "notes": data.notes},
        "created_at": _now_iso(),
    })
    return {"ok": True, "contract": contract}


@hotel_router.post("/{contract_id}/reject")
async def hotel_reject_request(
    contract_id: str,
    data: RejectRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    tenant_id = _require_hotel_user(current_user)
    sysdb = get_system_db()
    # ATOMIC find-and-update
    contract = await sysdb.agency_contracts.find_one_and_update(
        {"id": contract_id, "tenant_id": tenant_id, "status": "pending"},
        {"$set": {
            "status": "rejected",
            "decided_at": _now_iso(),
            "decided_by": current_user.email,
            "decision_notes": data.reason or "Sebep belirtilmedi",
            "updated_at": _now_iso(),
        }},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not contract:
        # Var mı diye bak — yok mu, yoksa durumu mu değişti?
        any_doc = await sysdb.agency_contracts.find_one(
            {"id": contract_id, "tenant_id": tenant_id}, {"_id": 0, "status": 1}
        )
        if not any_doc:
            raise HTTPException(404, "Sözleşme bulunamadı")
        raise HTTPException(409, f"Bu sözleşme zaten '{any_doc['status']}' durumunda")

    await sysdb.agency_contract_events.insert_one({
        "id": _uuid(),
        "contract_id": contract_id,
        "agency_id": contract["agency_id"],
        "tenant_id": tenant_id,
        "event": "rejected",
        "actor": current_user.email,
        "payload": {"reason": data.reason},
        "created_at": _now_iso(),
    })
    return {"ok": True, "contract": contract}


@hotel_router.post("/{contract_id}/terminate")
async def hotel_terminate_contract(
    contract_id: str,
    data: TerminateRequest,
    current_user: User = Depends(get_current_user),
):
    """Onaylı bir sözleşmeyi feshet (yeni rezervasyonlar engellenir,
    var olan rezervasyonlar etkilenmez)."""
    tenant_id = _require_hotel_user(current_user)
    sysdb = get_system_db()
    existing = await sysdb.agency_contracts.find_one(
        {"id": contract_id, "tenant_id": tenant_id},
        {"_id": 0, "decision_notes": 1, "status": 1}
    )
    if not existing:
        raise HTTPException(404, "Sözleşme bulunamadı")

    new_valid_to = data.effective_date or datetime.now(UTC).strftime("%Y-%m-%d")
    new_notes = (existing.get("decision_notes", "") + "\n[FESİH] " + (data.reason or "")).strip()

    contract = await sysdb.agency_contracts.find_one_and_update(
        {"id": contract_id, "tenant_id": tenant_id, "status": "approved"},
        {"$set": {
            "status": "terminated",
            "terminated_at": _now_iso(),
            "terminated_by": current_user.email,
            "decision_notes": new_notes,
            "valid_to": new_valid_to,
            "updated_at": _now_iso(),
        }},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not contract:
        raise HTTPException(409, f"Sadece onaylı sözleşmeler feshedilebilir (mevcut durum: {existing['status']})")

    await sysdb.agency_contract_events.insert_one({
        "id": _uuid(),
        "contract_id": contract_id,
        "agency_id": contract["agency_id"],
        "tenant_id": tenant_id,
        "event": "terminated",
        "actor": current_user.email,
        "payload": {"reason": data.reason, "effective_date": new_valid_to},
        "created_at": _now_iso(),
    })
    return {"ok": True, "contract": contract}


# ═══════════════════════════════════════════════════════════════════════
# ADMIN — One-shot migration: legacy aktif acentelere approved sözleşme oluştur
# ═══════════════════════════════════════════════════════════════════════

admin_router = APIRouter(prefix="/api/marketplace/v1/admin", tags=["Marketplace v1 / Admin"])


@admin_router.post("/migrate-existing-agencies")
async def migrate_existing_agencies(
    _: bool = Depends(__import__("routers.marketplace_b2b", fromlist=["_require_system_admin"])._require_system_admin),
):
    """Var olan tüm aktif (agency, listing) çiftleri için 'approved' sözleşme
    oluşturur. Idempotent — aynı çift için zaten sözleşme varsa atlar.

    Geçiş bittikten sonra bu endpoint'i tekrar çağırmak güvenli (no-op).
    """
    sysdb = get_system_db()
    await _ensure_indexes()  # Migration öncesi unique index garanti

    agencies = await sysdb.marketplace_agencies.find(
        {"status": "active"}, {"_id": 0}
    ).to_list(10000)
    listings = await sysdb.marketplace_listings.find(
        {"is_listed": True}, {"_id": 0}
    ).to_list(10000)

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    far_future = (datetime.now(UTC) + timedelta(days=730)).strftime("%Y-%m-%d")
    created = 0
    skipped = 0
    for ag in agencies:
        for ls in listings:
            cid = _uuid()
            code = await _next_contract_code(sysdb)
            commission = ls.get("commission_pct") or ag.get("default_commission_pct", 12.0)
            try:
                await sysdb.agency_contracts.insert_one({
                    "id": cid,
                    "contract_code": code,
                    "agency_id": ag["id"],
                    "agency_name": ag.get("name", ""),
                    "agency_country": ag.get("country", ""),
                    "agency_email": ag.get("contact_email", ""),
                    "tenant_id": ls["tenant_id"],
                    "hotel_name": ls.get("hotel_name", ""),
                    "hotel_city": ls.get("city", ""),
                    "status": "approved",
                    "commission_pct": commission,
                    "agency_proposed_commission_pct": commission,
                    "hotel_approved_commission_pct": commission,
                    "cancellation_policy": {
                        "free_until_days_before": 7,
                        "penalty_pct": 50.0,
                        "no_show_penalty_pct": 100.0,
                    },
                    "payment_terms": "on_arrival",
                    "valid_from": today,
                    "valid_to": far_future,
                    "currency": "TRY",
                    "allowed_room_types": ls.get("allowed_room_types", []),
                    "special_terms": "Otomatik geçiş — eski marketplace açık ilişkisinden",
                    "proposed_at": _now_iso(),
                    "proposed_by_email": "migration@syroce.com",
                    "decided_at": _now_iso(),
                    "decided_by": "migration@syroce.com",
                    "decision_notes": "Sözleşme-tabanlı pazaryerine geçişte otomatik onaylandı",
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                    "is_migration": True,
                })
                created += 1
            except DuplicateKeyError:
                # Zaten pending/approved sözleşme var → atla
                skipped += 1

    return {"ok": True, "created": created, "skipped": skipped,
            "total_agencies": len(agencies), "total_listings": len(listings)}


# ─── Tek bir router objesi expose et (registry için) ──────────────────────

# Birden fazla prefix var; registry'ye ayrı ayrı ekleyeceğiz.
__all__ = ["agency_router", "hotel_router", "admin_router",
           "has_active_contract", "list_partner_tenant_ids"]
