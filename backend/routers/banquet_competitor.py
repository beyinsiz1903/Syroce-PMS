"""Banquet-specific competitor analysis.

Tracks competing venues for banquet/event business and per-event-type
pricing snapshots, then renders a small positioning view comparing our
own per-pax averages to competitor bands.

To avoid creating new MongoDB collections (the Atlas cluster is at its
collection cap), this module piggybacks on the existing ``mice_accounts``
collection with an ``account_type="banquet_competitor"`` discriminator,
and embeds rate snapshots inside each competitor document under a
``competitor_rates`` array. The CRM accounts list excludes records of
this discriminator so the two concerns stay visually separate.

All endpoints are tenant-scoped and require an authenticated user.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.spa_mice_authz import require_mice_ops
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/banquet", tags=["banquet-competitor"])

ACCOUNT_TYPE = "banquet_competitor"


# ── Models ──────────────────────────────────────────────────────
class CompetitorIn(BaseModel):
    name: str
    hotel_class: int = Field(4, ge=0, le=7)  # star rating
    capacity_max: int = Field(0, ge=0)
    venues: list[str] = Field(default_factory=list)  # named function rooms
    notes: str | None = None
    active: bool = True


class CompetitorRateIn(BaseModel):
    event_type: str = "meeting"  # meeting/conference/wedding/gala/training/other
    season: str = "all"  # all / high / shoulder / low
    per_pax_price: float = Field(0, ge=0)
    currency: str = "TRY"
    min_pax: int = Field(0, ge=0)
    max_pax: int = Field(0, ge=0)
    package_includes: list[str] = Field(default_factory=list)
    source: str | None = None  # web / phone / lost-deal / other
    note: str | None = None


def _strip_internal(doc: dict) -> dict:
    """Drop Mongo-internal fields before returning to clients."""
    doc.pop("_id", None)
    return doc


# ── Competitor CRUD ─────────────────────────────────────────────
@router.get("/competitors")
async def list_competitors(
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    cur = db.mice_accounts.find(
        {"tenant_id": current_user.tenant_id,
         "account_type": ACCOUNT_TYPE},
        {"_id": 0}).sort("name", 1)
    return {"competitors": [d async for d in cur]}


@router.post("/competitors", status_code=201)
async def create_competitor(
    body: CompetitorIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "account_type": ACCOUNT_TYPE,
        **body.model_dump(),
        "competitor_rates": [],
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.username,
    }
    await db.mice_accounts.insert_one(doc)
    return _strip_internal(doc)


@router.put("/competitors/{competitor_id}")
async def update_competitor(
    competitor_id: str, body: CompetitorIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    res = await db.mice_accounts.update_one(
        {"id": competitor_id, "tenant_id": current_user.tenant_id,
         "account_type": ACCOUNT_TYPE},
        {"$set": {**body.model_dump(),
                  "updated_at": datetime.now(UTC).isoformat()}})
    if not res.matched_count:
        raise HTTPException(404, "Rakip bulunamadı")
    return {"ok": True}


@router.delete("/competitors/{competitor_id}")
async def delete_competitor(
    competitor_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    res = await db.mice_accounts.delete_one(
        {"id": competitor_id, "tenant_id": current_user.tenant_id,
         "account_type": ACCOUNT_TYPE})
    if not res.deleted_count:
        raise HTTPException(404, "Rakip bulunamadı")
    return {"ok": True}


# ── Rate snapshots (embedded in competitor doc) ─────────────────
@router.post("/competitors/{competitor_id}/rates", status_code=201)
async def add_rate(
    competitor_id: str, body: CompetitorRateIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    rate = {
        "id": str(uuid.uuid4()),
        **body.model_dump(),
        "recorded_at": datetime.now(UTC).isoformat(),
        "recorded_by": current_user.username,
    }
    res = await db.mice_accounts.update_one(
        {"id": competitor_id, "tenant_id": current_user.tenant_id,
         "account_type": ACCOUNT_TYPE},
        {"$push": {"competitor_rates": {
            "$each": [rate],
            "$position": 0,  # newest first → cheap latest-N reads
            "$slice": 200,   # cap history length
        }}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Rakip bulunamadı")
    return rate


@router.get("/competitors/{competitor_id}/rates")
async def list_rates(
    competitor_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    doc = await db.mice_accounts.find_one(
        {"id": competitor_id, "tenant_id": current_user.tenant_id,
         "account_type": ACCOUNT_TYPE},
        {"_id": 0, "competitor_rates": 1})
    if not doc:
        raise HTTPException(404, "Rakip bulunamadı")
    rates = (doc.get("competitor_rates") or [])[:limit]
    return {"rates": rates}


@router.delete("/competitors/{competitor_id}/rates/{rate_id}")
async def delete_rate(
    competitor_id: str, rate_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_mice_ops(current_user)
    db = get_system_db()
    res = await db.mice_accounts.update_one(
        {"id": competitor_id, "tenant_id": current_user.tenant_id,
         "account_type": ACCOUNT_TYPE},
        {"$pull": {"competitor_rates": {"id": rate_id}}})
    if not res.matched_count:
        raise HTTPException(404, "Rakip bulunamadı")
    return {"ok": True}


# ── Positioning ─────────────────────────────────────────────────
@router.get("/competitor-positioning")
async def positioning(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Per-event-type comparison: our recent average per-pax revenue
    (events table) vs competitor min/avg/max rate snapshots (embedded).
    """
    db = get_system_db()
    tenant_id = current_user.tenant_id

    # Aggregate over embedded competitor_rates arrays.
    pipe = [
        {"$match": {"tenant_id": tenant_id,
                     "account_type": ACCOUNT_TYPE}},
        {"$unwind": {"path": "$competitor_rates",
                       "preserveNullAndEmptyArrays": False}},
        {"$group": {
            "_id": "$competitor_rates.event_type",
            "competitor_min": {"$min": "$competitor_rates.per_pax_price"},
            "competitor_max": {"$max": "$competitor_rates.per_pax_price"},
            "competitor_avg": {"$avg": "$competitor_rates.per_pax_price"},
            "competitor_count": {"$sum": 1},
        }},
    ]
    competitor_summary: dict[str, dict] = {}
    async for r in db.mice_accounts.aggregate(pipe):
        competitor_summary[r["_id"]] = {
            "competitor_min": round(r.get("competitor_min") or 0, 2),
            "competitor_max": round(r.get("competitor_max") or 0, 2),
            "competitor_avg": round(r.get("competitor_avg") or 0, 2),
            "competitor_count": r.get("competitor_count") or 0,
        }

    # Our own per-event-type avg per-pax revenue (events with pax > 0).
    our_pipe = [
        {"$match": {"tenant_id": tenant_id,
                     "status": {"$in": ["definite", "confirmed", "completed"]},
                     "expected_pax": {"$gt": 0}}},
        {"$project": {
            "event_type": 1,
            "per_pax": {
                "$cond": [
                    {"$gt": ["$expected_pax", 0]},
                    {"$divide": [
                        {"$ifNull": ["$totals.grand_total", 0]},
                        "$expected_pax",
                    ]},
                    0,
                ],
            },
        }},
        {"$group": {
            "_id": "$event_type",
            "our_avg_per_pax": {"$avg": "$per_pax"},
            "events_count": {"$sum": 1},
        }},
    ]
    our_summary: dict[str, dict] = {}
    async for r in db.mice_events.aggregate(our_pipe):
        our_summary[r["_id"]] = {
            "our_avg_per_pax": round(r.get("our_avg_per_pax") or 0, 2),
            "events_count": r.get("events_count") or 0,
        }

    event_types = sorted(set(competitor_summary) | set(our_summary))
    rows: list[dict[str, Any]] = []
    for et in event_types:
        cs = competitor_summary.get(et, {})
        os_ = our_summary.get(et, {})
        our_avg = os_.get("our_avg_per_pax") or 0
        comp_avg = cs.get("competitor_avg") or 0
        position = "no_data"
        if comp_avg > 0 and our_avg > 0:
            if our_avg < comp_avg * 0.9:
                position = "below_market"
            elif our_avg > comp_avg * 1.1:
                position = "above_market"
            else:
                position = "in_band"
        rows.append({
            "event_type": et,
            **cs,
            **os_,
            "position": position,
        })
    return {
        "rows": rows,
        "tenant_id": tenant_id,
        "computed_at": datetime.now(UTC).isoformat(),
    }
