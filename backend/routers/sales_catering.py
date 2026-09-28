"""Sales & Catering — Opportunity pipeline and packages on top of MICE.

Closes the gap with OPERA Sales & Catering:
* Opportunity lifecycle: lead → qualified → proposal → contract → won / lost
* Activity log per opportunity (call/email/meeting/site-visit)
* Pipeline summary (count + value per stage)
* Wedding / conference / corporate packages (bundled spaces + menus + rooms)
* Optional linkage between opportunity → MICE event → group room block

Authorisation reuses existing MICE roles via require_mice_ops.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.audit import log_audit_event
from core.database import db
from core.entitlements.enforcement import require_feature
from core.security import get_current_user
from core.spa_mice_authz import require_catalog, require_mice_ops
from core.tenant_currency import get_tenant_currency
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v95 DW

router = APIRouter(prefix="/api/mice/sales", tags=["sales-catering"])

STAGES = ("lead", "qualified", "proposal", "contract", "won", "lost")
ACTIVITY_TYPES = ("call", "email", "meeting", "site_visit", "note", "task")
PACKAGE_TYPES = ("wedding", "conference", "corporate", "social", "incentive")

# mice_opportunities/mice_opportunity_activities koleksiyonları, Atlas
# 500 limiti dolduğu için Sales CRM (domains/sales/router.py) ile
# paylaşılır. Onlar _kind="lead" ile yazar; biz "opportunity" yazıp
# sorgularda lead'leri hariç tutarız.
_NOT_LEAD = {"$ne": "lead"}


_indexes_ready = False


def _normalize_currency(value: str | None, fallback: str) -> str:
    code = str(value or fallback).strip().upper()
    if len(code) != 3 or not code.isascii() or not code.isalpha():
        raise HTTPException(422, "Para birimi 3 harfli bir kod olmalıdır (örn. TRY, EUR, USD)")
    return code


async def _tenant_currency_code(tenant_id: str) -> str:
    code, _symbol = await get_tenant_currency(tenant_id)
    return _normalize_currency(code, "TRY")


async def _currency_payload(payload: BaseModel, tenant_id: str) -> dict[str, Any]:
    data = payload.model_dump()
    data["currency"] = _normalize_currency(data.get("currency"), await _tenant_currency_code(tenant_id))
    return data


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await db.mice_opportunities.create_index(
            [("tenant_id", 1), ("stage", 1), ("created_at", -1)],
            name="opp_stage_date",
        )
        await db.mice_opportunities.create_index(
            [("tenant_id", 1), ("account_id", 1)],
            name="opp_account",
        )
        await db.mice_opportunity_activities.create_index(
            [("tenant_id", 1), ("opportunity_id", 1), ("created_at", -1)],
            name="opp_act",
        )
        await db.mice_packages.create_index(
            [("tenant_id", 1), ("type", 1), ("active", 1)],
            name="pkg_type",
        )
        _indexes_ready = True
    except Exception:
        pass


# ── Models ───────────────────────────────────────────────────────
class OpportunityIn(BaseModel):
    title: str
    account_id: str | None = None
    contact_id: str | None = None
    event_type: str | None = None  # wedding/conference/corporate/...
    expected_start: str | None = None  # ISO date
    expected_end: str | None = None
    pax: int = Field(0, ge=0)
    estimated_value: float = Field(0, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    probability: int = Field(50, ge=0, le=100)
    source: str | None = None  # referral, website, repeat, cold...
    owner: str | None = None  # user id of sales rep
    notes: str | None = None


class StageTransitionIn(BaseModel):
    to_stage: str
    reason: str | None = None
    won_event_id: str | None = None  # if winning, link to created MICE event
    group_block_id: str | None = None  # if winning, link group block


class ActivityIn(BaseModel):
    type: str = "note"
    subject: str | None = None
    body: str | None = None
    happened_at: str | None = None  # ISO
    duration_min: int = Field(0, ge=0)
    outcome: str | None = None  # positive/neutral/negative


class PackageItemIn(BaseModel):
    kind: str  # space / menu / room / resource / addon
    ref_id: str | None = None  # mice_spaces / mice_menus / room_type etc
    name: str
    quantity: float = 1
    unit_price: float = 0
    notes: str | None = None


class PackageIn(BaseModel):
    name: str
    type: str = "wedding"
    description: str | None = None
    min_pax: int = Field(0, ge=0)
    max_pax: int = Field(0, ge=0)
    base_price: float = Field(0, ge=0)
    per_pax_price: float = Field(0, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    items: list[PackageItemIn] = Field(default_factory=list)
    active: bool = True


# ── Opportunities ────────────────────────────────────────────────
@router.get("/opportunities", dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def list_opportunities(
    stage: str | None = Query(None),
    account_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    await _ensure_indexes()
    q: dict[str, Any] = {"_kind": _NOT_LEAD, "tenant_id": current_user.tenant_id}
    if stage:
        if stage not in STAGES:
            raise HTTPException(400, "Invalid stage")
        q["stage"] = stage
    if account_id:
        q["account_id"] = account_id

    cursor = db.mice_opportunities.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    opportunities = [o async for o in cursor]
    tenant_currency = await _tenant_currency_code(current_user.tenant_id)
    for opportunity in opportunities:
        opportunity["currency"] = _normalize_currency(opportunity.get("currency"), tenant_currency)
    return {"opportunities": opportunities}


@router.post("/opportunities", status_code=201, dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def create_opportunity(
    payload: OpportunityIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v95 DW
):
    require_mice_ops(current_user)
    await _ensure_indexes()
    now = datetime.now(UTC).isoformat()
    doc = {
        "_kind": "opportunity",
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "stage": "lead",
        "stage_history": [{"stage": "lead", "at": now, "by": getattr(current_user, "id", None)}],
        "created_at": now,
        "updated_at": now,
        "created_by": getattr(current_user, "id", None),
        **await _currency_payload(payload, current_user.tenant_id),
    }
    await db.mice_opportunities.insert_one(doc.copy())
    return doc


@router.get("/opportunities/{opp_id}", dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def get_opportunity(opp_id: str, current_user: User = Depends(get_current_user)):
    o = await db.mice_opportunities.find_one({"_kind": _NOT_LEAD, "id": opp_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Opportunity not found")
    o["currency"] = _normalize_currency(o.get("currency"), await _tenant_currency_code(current_user.tenant_id))
    acts = (
        await db.mice_opportunity_activities.find(
            {"_kind": _NOT_LEAD, "opportunity_id": opp_id, "tenant_id": current_user.tenant_id},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(200)
    )
    o["activities"] = acts
    return o


@router.put("/opportunities/{opp_id}", dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def update_opportunity(
    opp_id: str,
    payload: OpportunityIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v95 DW
):
    require_mice_ops(current_user)
    res = await db.mice_opportunities.update_one(
        {"_kind": _NOT_LEAD, "id": opp_id, "tenant_id": current_user.tenant_id},
        {"$set": {**await _currency_payload(payload, current_user.tenant_id), "updated_at": datetime.now(UTC).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Opportunity not found")
    return {"ok": True}


@router.delete("/opportunities/{opp_id}", dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def delete_opportunity(
    opp_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v95 DW
):
    require_mice_ops(current_user)
    res = await db.mice_opportunities.delete_one({"_kind": _NOT_LEAD, "id": opp_id, "tenant_id": current_user.tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Opportunity not found")
    return {"ok": True}


@router.post("/opportunities/{opp_id}/transition", dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def transition_stage(
    opp_id: str,
    payload: StageTransitionIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v95 DW
):
    require_mice_ops(current_user)
    if payload.to_stage not in STAGES:
        raise HTTPException(400, f"Invalid stage. One of: {STAGES}")
    o = await db.mice_opportunities.find_one({"_kind": _NOT_LEAD, "id": opp_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Opportunity not found")
    if o.get("stage") == payload.to_stage:
        return {"ok": True, "unchanged": True}

    now = datetime.now(UTC).isoformat()
    update: dict[str, Any] = {
        "stage": payload.to_stage,
        "updated_at": now,
        "probability": _stage_default_probability(payload.to_stage, o.get("probability", 50)),
    }
    if payload.won_event_id:
        update["won_event_id"] = payload.won_event_id
    if payload.group_block_id:
        update["group_block_id"] = payload.group_block_id
    if payload.to_stage in ("won", "lost"):
        update["closed_at"] = now
        update["close_reason"] = payload.reason

    await db.mice_opportunities.update_one(
        {"_kind": _NOT_LEAD, "id": opp_id, "tenant_id": current_user.tenant_id},
        {
            "$set": update,
            "$push": {
                "stage_history": {
                    "stage": payload.to_stage,
                    "at": now,
                    "by": getattr(current_user, "id", None),
                    "reason": payload.reason,
                }
            },
        },
    )

    try:
        await log_audit_event(
            current_user.tenant_id,
            actor_user_id=getattr(current_user, "id", None) or "",
            action=f"sales.opp.{payload.to_stage}",
            entity_type="mice_opportunity",
            entity_id=opp_id,
            metadata={"from": o.get("stage"), "to": payload.to_stage, "reason": payload.reason},
            severity="low",
        )
    except Exception:
        pass

    return {"ok": True, "stage": payload.to_stage}


def _stage_default_probability(stage: str, current: int) -> int:
    return {
        "lead": 10,
        "qualified": 25,
        "proposal": 50,
        "contract": 80,
        "won": 100,
        "lost": 0,
    }.get(stage, current)


@router.post("/opportunities/{opp_id}/activities", status_code=201, dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def add_activity(
    opp_id: str,
    payload: ActivityIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v95 DW
):
    require_mice_ops(current_user)
    if payload.type not in ACTIVITY_TYPES:
        raise HTTPException(400, f"Invalid activity type. One of: {ACTIVITY_TYPES}")
    o = await db.mice_opportunities.find_one({"_kind": _NOT_LEAD, "id": opp_id, "tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1})
    if not o:
        raise HTTPException(404, "Opportunity not found")

    now = datetime.now(UTC).isoformat()
    doc = {
        "_kind": "opportunity_activity",
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "opportunity_id": opp_id,
        "created_at": now,
        "created_by": getattr(current_user, "id", None),
        **payload.model_dump(),
    }
    if not doc.get("happened_at"):
        doc["happened_at"] = now
    await db.mice_opportunity_activities.insert_one(doc.copy())
    return doc


# ── Pipeline summary ─────────────────────────────────────────────
@router.get("/pipeline", dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def pipeline_summary(current_user: User = Depends(get_current_user)):
    tenant_currency = await _tenant_currency_code(current_user.tenant_id)
    pipeline = [
        {"$match": {"_kind": _NOT_LEAD, "tenant_id": current_user.tenant_id}},
        {
            "$group": {
                "_id": {
                    "stage": "$stage",
                    "currency": {"$toUpper": {"$ifNull": ["$currency", tenant_currency]}},
                },
                "count": {"$sum": 1},
                "total_value": {"$sum": {"$ifNull": ["$estimated_value", 0]}},
                "weighted_value": {
                    "$sum": {
                        "$multiply": [
                            {"$ifNull": ["$estimated_value", 0]},
                            {"$divide": [{"$ifNull": ["$probability", 0]}, 100]},
                        ]
                    }
                },
                "total_pax": {"$sum": {"$ifNull": ["$pax", 0]}},
            }
        },
    ]
    cursor = db.mice_opportunities.aggregate(pipeline)
    by_stage: dict[str, dict[str, Any]] = {}
    async for row in cursor:
        group = row.pop("_id") or {}
        stage = group.get("stage") if isinstance(group, dict) else group
        currency = _normalize_currency(group.get("currency") if isinstance(group, dict) else None, tenant_currency)
        bucket = by_stage.setdefault(stage or "unknown", {
            "count": 0, "total_value": 0, "weighted_value": 0, "total_pax": 0,
            "total_value_by_currency": {}, "weighted_value_by_currency": {},
        })
        total = round(row.get("total_value", 0), 2)
        weighted = round(row.get("weighted_value", 0), 2)
        bucket["count"] += row.get("count", 0)
        bucket["total_pax"] += row.get("total_pax", 0)
        bucket["total_value_by_currency"][currency] = total
        bucket["weighted_value_by_currency"][currency] = weighted
        # Preserve scalar compatibility for the tenant's configured base bucket.
        if currency == tenant_currency:
            bucket["total_value"] = total
            bucket["weighted_value"] = weighted

    stages = [
        {
            "stage": s,
            **by_stage.get(
                s,
                {
                    "count": 0,
                    "total_value": 0,
                    "weighted_value": 0,
                    "total_pax": 0,
                    "total_value_by_currency": {},
                    "weighted_value_by_currency": {},
                },
            ),
        }
        for s in STAGES
    ]

    open_value = sum(s["total_value"] for s in stages if s["stage"] not in ("won", "lost"))
    weighted_open = sum(s["weighted_value"] for s in stages if s["stage"] not in ("won", "lost"))
    won_value = next((s["total_value"] for s in stages if s["stage"] == "won"), 0)
    lost_value = next((s["total_value"] for s in stages if s["stage"] == "lost"), 0)
    closed = won_value + lost_value
    win_rate = round((won_value / closed) * 100, 2) if closed > 0 else 0

    def sum_breakdown(field: str, selected: set[str]) -> dict[str, float]:
        result: dict[str, float] = {}
        for stage in stages:
            if stage["stage"] not in selected:
                continue
            for currency, amount in stage.get(field, {}).items():
                result[currency] = round(result.get(currency, 0) + amount, 2)
        return result

    open_stages = set(STAGES) - {"won", "lost"}

    return {
        "stages": stages,
        "open_value": round(open_value, 2),
        "weighted_open_value": round(weighted_open, 2),
        "won_value": round(won_value, 2),
        "lost_value": round(lost_value, 2),
        "open_value_by_currency": sum_breakdown("total_value_by_currency", open_stages),
        "weighted_open_value_by_currency": sum_breakdown("weighted_value_by_currency", open_stages),
        "won_value_by_currency": sum_breakdown("total_value_by_currency", {"won"}),
        "lost_value_by_currency": sum_breakdown("total_value_by_currency", {"lost"}),
        "win_rate_pct": win_rate,
    }


# ── Packages ─────────────────────────────────────────────────────
@router.get("/packages")
async def list_packages(
    type: str | None = Query(None),
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
):
    await _ensure_indexes()
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if type:
        if type not in PACKAGE_TYPES:
            raise HTTPException(400, f"Invalid type. One of: {PACKAGE_TYPES}")
        q["type"] = type
    if active_only:
        q["active"] = True
    cursor = db.mice_packages.find(q, {"_id": 0}).sort("name", 1)
    packages = [p async for p in cursor]
    tenant_currency = await _tenant_currency_code(current_user.tenant_id)
    for package in packages:
        package["currency"] = _normalize_currency(package.get("currency"), tenant_currency)
    return {"packages": packages}


@router.post("/packages", status_code=201)
async def create_package(
    payload: PackageIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    require_catalog(current_user)
    if payload.type not in PACKAGE_TYPES:
        raise HTTPException(400, f"Invalid type. One of: {PACKAGE_TYPES}")
    await _ensure_indexes()
    now = datetime.now(UTC).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "created_at": now,
        "updated_at": now,
        **await _currency_payload(payload, current_user.tenant_id),
    }
    await db.mice_packages.insert_one(doc.copy())
    return doc


@router.put("/packages/{pkg_id}")
async def update_package(
    pkg_id: str,
    payload: PackageIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    require_catalog(current_user)
    if payload.type not in PACKAGE_TYPES:
        raise HTTPException(400, f"Invalid type. One of: {PACKAGE_TYPES}")
    res = await db.mice_packages.update_one(
        {"id": pkg_id, "tenant_id": current_user.tenant_id},
        {"$set": {**await _currency_payload(payload, current_user.tenant_id), "updated_at": datetime.now(UTC).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Package not found")
    return {"ok": True}


@router.delete("/packages/{pkg_id}")
async def delete_package(
    pkg_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    require_catalog(current_user)
    res = await db.mice_packages.delete_one({"id": pkg_id, "tenant_id": current_user.tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Package not found")
    return {"ok": True}


@router.post("/packages/{pkg_id}/quote", dependencies=[Depends(require_feature("mice", "proposals_contracts"))])
async def quote_package(
    pkg_id: str,
    pax: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v95 DW
):
    """Compute a price quote for a package given pax count."""
    pkg = await db.mice_packages.find_one({"id": pkg_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not pkg:
        raise HTTPException(404, "Package not found")

    base = float(pkg.get("base_price", 0))
    per_pax = float(pkg.get("per_pax_price", 0))
    items_total = sum(float(it.get("quantity", 1)) * float(it.get("unit_price", 0)) for it in pkg.get("items", []))
    subtotal = base + (per_pax * pax) + items_total

    return {
        "package_id": pkg_id,
        "package_name": pkg.get("name"),
        "pax": pax,
        "currency": _normalize_currency(pkg.get("currency"), await _tenant_currency_code(current_user.tenant_id)),
        "breakdown": {
            "base_price": round(base, 2),
            "per_pax_total": round(per_pax * pax, 2),
            "items_total": round(items_total, 2),
        },
        "subtotal": round(subtotal, 2),
    }
