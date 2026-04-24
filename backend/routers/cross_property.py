"""Cross-Property Guest & Loyalty Network.

Chain-wide guest profile resolution for multi-property hotel groups.
Mirrors Marriott Bonvoy / Hilton Honors / OPERA Cloud Loyalty:
* Single guest record valid across all properties in a chain
* Search across all chain-member tenants
* Unified profile (lifetime stays, total spend, properties visited)
* Loyalty summary (which guests stay at multiple properties)
* Merge duplicate guest profiles

Chain membership is determined by:
* `tenants.chain_id` field (siblings share the same chain_id)
* OR a user with `super_admin` role sees all tenants
* Falls back to current tenant only when no chain context exists
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from cache_manager import cached as _cached
from core.audit import log_audit_event
from core.security import get_current_user
from core.spa_mice_authz import require_roles
from core.tenant_db import get_system_db
from models.schemas import User, UserRole
from modules.pms_core.role_permission_service import require_op  # v76 Bug DL

# Cross-property by definition spans tenants — bypass the per-tenant guard
# by using the raw system motor handle. We re-apply chain scoping ourselves
# via _chain_tenant_ids() on every query.
db = get_system_db()

router = APIRouter(prefix="/api/cross-property", tags=["cross-property"])


# ── Chain resolution ─────────────────────────────────────────────
async def _chain_tenant_ids(current_user: User) -> list[str]:
    """Return the list of tenant_ids the current user can see across the chain.

    Super admins see every tenant. Regular users see only tenants in the same
    chain (matching `chain_id` on the tenants doc). If no chain_id is set,
    they see only their own tenant.
    """
    role = getattr(current_user, "role", None) or ""
    if role == "super_admin":
        cursor = db.tenants.find({}, {"_id": 0, "tenant_id": 1})
        ids = [t["tenant_id"] async for t in cursor if t.get("tenant_id")]
        return ids or [current_user.tenant_id]

    own = await db.tenants.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "chain_id": 1},
    )
    chain_id = (own or {}).get("chain_id")
    if not chain_id:
        return [current_user.tenant_id]

    cursor = db.tenants.find({"chain_id": chain_id}, {"_id": 0, "tenant_id": 1})
    ids = [t["tenant_id"] async for t in cursor if t.get("tenant_id")]
    return ids or [current_user.tenant_id]


async def _tenant_name_map(tenant_ids: list[str]) -> dict[str, str]:
    cursor = db.tenants.find(
        {"tenant_id": {"$in": tenant_ids}},
        {"_id": 0, "tenant_id": 1, "hotel_name": 1, "name": 1},
    )
    out: dict[str, str] = {}
    async for t in cursor:
        tid = t.get("tenant_id")
        if tid:
            out[tid] = t.get("hotel_name") or t.get("name") or tid
    return out


# ── Guest search ─────────────────────────────────────────────────
@router.get("/guests/search")
async def search_chain_guests(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Search guests across all chain-member properties by name/email/phone."""
    tenant_ids = await _chain_tenant_ids(current_user)
    safe = re.escape(q.strip())
    rx = {"$regex": safe, "$options": "i"}

    query = {
        "tenant_id": {"$in": tenant_ids},
        "$or": [
            {"name": rx},
            {"first_name": rx},
            {"last_name": rx},
            {"email": rx},
            {"phone": rx},
        ],
    }
    cursor = db.guests.find(
        query,
        {
            "_id": 0,
            "id": 1, "guest_id": 1, "tenant_id": 1,
            "name": 1, "first_name": 1, "last_name": 1,
            "email": 1, "phone": 1, "loyalty_tier": 1,
        },
    ).limit(limit)

    raw = [g async for g in cursor]
    name_map = await _tenant_name_map(tenant_ids)

    # cross-property dedupe: count distinct emails/phones appearing in >1 tenant
    by_key: dict[str, set[str]] = {}
    guests_out: list[dict[str, Any]] = []
    for g in raw:
        gid = g.get("id") or g.get("guest_id")
        full_name = g.get("name") or " ".join(
            x for x in [g.get("first_name"), g.get("last_name")] if x
        ).strip() or "(isimsiz)"
        email = (g.get("email") or "").lower().strip()
        phone = (g.get("phone") or "").strip()
        key = email or phone
        tid = g.get("tenant_id")
        if key and tid:
            by_key.setdefault(key, set()).add(tid)
        guests_out.append({
            "id": gid,
            "name": full_name,
            "email": g.get("email"),
            "phone": g.get("phone"),
            "tenant_id": tid,
            "property_name": name_map.get(tid, tid),
            "loyalty_tier": g.get("loyalty_tier"),
        })

    cross_matches = sum(1 for tids in by_key.values() if len(tids) > 1)
    return {
        "total": len(guests_out),
        "cross_property_matches": cross_matches,
        "chain_size": len(tenant_ids),
        "guests": guests_out,
    }


# ── Unified guest profile ────────────────────────────────────────
@router.get("/guests/profile/{guest_id}")
async def get_unified_profile(
    guest_id: str,
    current_user: User = Depends(get_current_user),
):
    """Resolve all guest records (across the chain) tied to this person and
    return a single merged profile with lifetime stay history."""
    tenant_ids = await _chain_tenant_ids(current_user)

    # 1) Find the seed guest doc within the chain
    seed = await db.guests.find_one(
        {
            "$or": [{"id": guest_id}, {"guest_id": guest_id}],
            "tenant_id": {"$in": tenant_ids},
        },
        {"_id": 0},
    )
    if not seed:
        raise HTTPException(status_code=404, detail="Guest not found in chain")

    email = (seed.get("email") or "").strip().lower()
    phone = (seed.get("phone") or "").strip()

    # 2) Locate every guest doc with the same email/phone in the chain
    or_clauses: list[dict[str, Any]] = []
    if email:
        or_clauses.append({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})
    if phone:
        or_clauses.append({"phone": phone})
    or_clauses.append({"id": guest_id})
    or_clauses.append({"guest_id": guest_id})

    related_cursor = db.guests.find(
        {"tenant_id": {"$in": tenant_ids}, "$or": or_clauses},
        {"_id": 0, "id": 1, "guest_id": 1, "tenant_id": 1},
    )
    related_ids: list[str] = []
    related_tenants: set[str] = set()
    async for g in related_cursor:
        gid = g.get("id") or g.get("guest_id")
        if gid:
            related_ids.append(gid)
        tid = g.get("tenant_id")
        if tid:
            related_tenants.add(tid)

    # 3) Aggregate stay history from bookings
    name_map = await _tenant_name_map(list(related_tenants) or tenant_ids)
    booking_query = {
        "tenant_id": {"$in": tenant_ids},
        "$or": [
            {"guest_id": {"$in": related_ids}} if related_ids else {"guest_id": guest_id},
            {"guest_email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}
            if email else {"_no_op": True},
        ],
    }
    bookings_cursor = db.bookings.find(
        booking_query,
        {
            "_id": 0,
            "id": 1, "tenant_id": 1, "check_in": 1, "check_out": 1,
            "room_number": 1, "room_type": 1, "status": 1, "total_amount": 1,
            "nights": 1,
        },
    ).sort("check_in", -1).limit(200)

    stay_history: list[dict[str, Any]] = []
    total_spent = 0.0
    total_nights = 0
    properties_seen: set[str] = set()
    async for b in bookings_cursor:
        tid = b.get("tenant_id")
        properties_seen.add(tid or "")
        amt = float(b.get("total_amount") or 0)
        nights = int(b.get("nights") or 0)
        total_spent += amt
        total_nights += nights
        stay_history.append({
            "tenant_id": tid,
            "property_name": name_map.get(tid, tid),
            "check_in": b.get("check_in"),
            "check_out": b.get("check_out"),
            "room_number": b.get("room_number"),
            "room_type": b.get("room_type"),
            "status": b.get("status"),
            "total_amount": amt,
            "nights": nights,
        })

    full_name = seed.get("name") or " ".join(
        x for x in [seed.get("first_name"), seed.get("last_name")] if x
    ).strip()

    return {
        "guest": {
            "id": seed.get("id") or seed.get("guest_id"),
            "name": full_name,
            "email": seed.get("email"),
            "phone": seed.get("phone"),
            "loyalty_tier": seed.get("loyalty_tier"),
            "preferences": seed.get("preferences", {}),
        },
        "cross_property_records": len(related_ids),
        "linked_tenants": sorted(related_tenants),
        "lifetime_stats": {
            "total_stays": len(stay_history),
            "total_nights": total_nights,
            "total_spent": round(total_spent, 2),
            "properties_count": len([p for p in properties_seen if p]),
        },
        "stay_history": stay_history,
    }


# ── Chain loyalty summary ────────────────────────────────────────
@router.get("/guests/loyalty-summary")
@_cached(ttl=180, key_prefix="cross_loyalty_summary")
async def loyalty_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_guest_list")),  # v76 Bug DL: PII chain loyalty
):
    """Identify guests appearing at multiple chain properties (loyal travelers)."""
    tenant_ids = await _chain_tenant_ids(current_user)
    name_map = await _tenant_name_map(tenant_ids)

    pipeline = [
        {"$match": {
            "tenant_id": {"$in": tenant_ids},
            "email": {"$nin": [None, ""]},
        }},
        {"$group": {
            "_id": {"$toLower": "$email"},
            "name": {"$first": "$name"},
            "first_name": {"$first": "$first_name"},
            "last_name": {"$first": "$last_name"},
            "email": {"$first": "$email"},
            "tenants": {"$addToSet": "$tenant_id"},
            "total_records": {"$sum": 1},
            "tier": {"$max": "$loyalty_tier"},
        }},
        {"$match": {"$expr": {"$gt": [{"$size": "$tenants"}, 1]}}},
        {"$project": {
            "_id": 0,
            "email": 1,
            "name": {"$ifNull": ["$name", {"$concat": [
                {"$ifNull": ["$first_name", ""]}, " ",
                {"$ifNull": ["$last_name", ""]},
            ]}]},
            "tier": 1,
            "properties_count": {"$size": "$tenants"},
            "tenants": 1,
            "total_records": 1,
        }},
        {"$sort": {"properties_count": -1, "total_records": -1}},
        {"$limit": 100},
    ]

    cursor = db.guests.aggregate(pipeline)
    out: list[dict[str, Any]] = []
    async for row in cursor:
        row["properties"] = [
            {"tenant_id": t, "name": name_map.get(t, t)}
            for t in row.pop("tenants", [])
        ]
        out.append(row)

    return {
        "chain_size": len(tenant_ids),
        "loyal_guests_count": len(out),
        "loyal_guests": out,
    }


# ── Profile merge ────────────────────────────────────────────────
class MergeRequest(BaseModel):
    target_guest_id: str  # guest to merge into the primary
    keep_field_overrides: dict[str, Any] = {}


@router.post("/guests/{primary_id}/merge")
async def merge_guest_profiles(
    primary_id: str,
    payload: MergeRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Merge a duplicate guest profile into the primary record.

    The duplicate's bookings/folios are repointed to the primary guest_id,
    the duplicate doc is archived, and an audit event is emitted.
    Both records must belong to tenants the caller can access.
    """
    if primary_id == payload.target_guest_id:
        raise HTTPException(status_code=400, detail="Cannot merge a guest into itself")

    # Privilege gate — destructive cross-tenant op restricted to elevated roles
    require_roles(current_user, {
        UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPERVISOR,
    })

    tenant_ids = await _chain_tenant_ids(current_user)
    primary = await db.guests.find_one(
        {"$or": [{"id": primary_id}, {"guest_id": primary_id}],
         "tenant_id": {"$in": tenant_ids}},
        {"_id": 1, "tenant_id": 1, "id": 1, "guest_id": 1},
    )
    duplicate = await db.guests.find_one(
        {"$or": [{"id": payload.target_guest_id}, {"guest_id": payload.target_guest_id}],
         "tenant_id": {"$in": tenant_ids}},
        {"_id": 1, "tenant_id": 1, "id": 1, "guest_id": 1},
    )
    if not primary or not duplicate:
        raise HTTPException(status_code=404, detail="Primary or duplicate guest not found")

    primary_tenant = primary.get("tenant_id")
    dup_tenant = duplicate.get("tenant_id")

    # Canonicalize identifiers — guest docs may carry both `id` and `guest_id`,
    # and dependent records may reference either. Repoint by $in over every
    # known alias of the duplicate, set canonical primary id (prefer guest.id).
    dup_aliases = [v for v in {duplicate.get("id"), duplicate.get("guest_id"),
                                payload.target_guest_id} if v]
    primary_canonical = primary.get("id") or primary.get("guest_id") or primary_id

    repoint_q = {
        "tenant_id": dup_tenant,
        "guest_id": {"$in": dup_aliases},
    }
    booking_res = await db.bookings.update_many(
        repoint_q,
        {"$set": {"guest_id": primary_canonical,
                  "merged_from": payload.target_guest_id}},
    )
    folio_res = await db.folios.update_many(
        repoint_q,
        {"$set": {"guest_id": primary_canonical,
                  "merged_from": payload.target_guest_id}},
    )

    # Safety guard: if linked records exist under any alias but nothing was
    # repointed, abort archive to prevent orphaning.
    expected_bookings = await db.bookings.count_documents(
        {"tenant_id": dup_tenant, "guest_id": {"$in": dup_aliases}}
    )
    expected_folios = await db.folios.count_documents(
        {"tenant_id": dup_tenant, "guest_id": {"$in": dup_aliases}}
    )
    if (expected_bookings > 0 or expected_folios > 0) and \
       booking_res.modified_count == 0 and folio_res.modified_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Repoint produced no updates while linked records exist; aborted",
        )

    # Archive duplicate (soft delete) — pin to the immutable _id we resolved.
    # v109 round-9 IDOR DiD: also assert tenant on the update filter.
    await db.guests.update_one(
        {"_id": duplicate["_id"], "tenant_id": dup_tenant},
        {"$set": {
            "archived": True,
            "archived_at": datetime.now(UTC).isoformat(),
            "merged_into": primary_id,
        }},
    )

    # Apply optional field overrides on primary — pin to its immutable _id
    if payload.keep_field_overrides:
        safe = {k: v for k, v in payload.keep_field_overrides.items()
                if k in {"name", "first_name", "last_name", "email", "phone",
                         "loyalty_tier", "preferences", "vip", "company"}}
        if safe:
            await db.guests.update_one(
                {"_id": primary["_id"], "tenant_id": primary.get("tenant_id")},
                {"$set": safe},
            )

    try:
        await log_audit_event(
            current_user.tenant_id,
            actor_user_id=getattr(current_user, "id", None) or "",
            action="cross_property.guest_merge",
            entity_type="guest",
            entity_id=primary_id,
            metadata={
                "duplicate_id": payload.target_guest_id,
                "primary_tenant": primary_tenant,
                "duplicate_tenant": dup_tenant,
                "bookings_repointed": booking_res.modified_count,
                "folios_repointed": folio_res.modified_count,
            },
            severity="medium",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "primary_id": primary_id,
        "archived_id": payload.target_guest_id,
        "bookings_repointed": booking_res.modified_count,
        "folios_repointed": folio_res.modified_count,
    }
