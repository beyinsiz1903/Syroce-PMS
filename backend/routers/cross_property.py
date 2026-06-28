"""Cross-Property Guest & Loyalty Network.

Chain-wide guest profile resolution for multi-property hotel groups.
Mirrors Marriott Bonvoy / Hilton Honors / OPERA Cloud Loyalty:
* Single guest record valid across all properties in a chain
* Search across all chain-member tenants
* Unified profile (lifetime stays, total spend, properties visited)
* Loyalty summary (which guests stay at multiple properties)
* Merge duplicate guest profiles

Chain membership is determined purely by the `tenants.chain_id` field
(siblings share the same chain_id). The `super_admin` role grants no
extra cross-tenant visibility on this endpoint — an unchained tenant
sees only itself even when the caller is a super_admin. This avoids
the F8AH P0 leak where a super_admin on an unchained ops/pilot tenant
saw every tenant in the system.
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

    # v97 fix — tenants koleksiyonu üyelerin büyük kısmı `id` field'ı
    # kullanıyor (sadece 1/40 doc'ta `tenant_id` mevcut). İkisini birden
    # destekle ki super_admin chain view ve chain_id resolution çalışsın.
    def _tid(t: dict) -> str | None:
        return t.get("tenant_id") or t.get("id")

    # F8AH P0 fix — even a super_admin must NOT see foreign tenants unless
    # their OWN tenant explicitly declares a `chain_id`. The previous
    # behaviour returned every tenant in the system for any super_admin,
    # collapsing the tenant boundary whenever an ops/pilot user happened
    # to hold the role (threat_model.md § Information Disclosure /
    # cross-tenant exposure). Chain scope is now purely chain_id-driven
    # for everyone; the super_admin role only widens scope WITHIN the
    # chain (and is otherwise a no-op for unchained tenants).
    own = await db.tenants.find_one(
        {"$or": [{"tenant_id": current_user.tenant_id}, {"id": current_user.tenant_id}]},
        {"_id": 0, "chain_id": 1},
    )
    chain_id = (own or {}).get("chain_id")
    if not chain_id:
        return [current_user.tenant_id]

    cursor = db.tenants.find(
        {"chain_id": chain_id},
        {"_id": 0, "tenant_id": 1, "id": 1},
    )
    ids = [_tid(t) async for t in cursor]
    ids = [x for x in ids if x]
    return ids or [current_user.tenant_id]


async def _tenant_name_map(tenant_ids: list[str]) -> dict[str, str]:
    # v97 fix — match by either tenant_id or id (see above).
    cursor = db.tenants.find(
        {"$or": [{"tenant_id": {"$in": tenant_ids}}, {"id": {"$in": tenant_ids}}]},
        {"_id": 0, "tenant_id": 1, "id": 1, "hotel_name": 1, "name": 1},
    )
    out: dict[str, str] = {}
    async for t in cursor:
        tid = t.get("tenant_id") or t.get("id")
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

    from security.encrypted_lookup import decrypt_guest_doc, guest_pii_regex_or_conditions

    # Dual-read: email/phone are encrypted at-rest, so a plaintext regex alone can
    # never match an encrypted row. guest_pii_regex_or_conditions adds the exact
    # blind-index hash branch (full-value match) while keeping the legacy regex
    # branch for not-yet-backfilled plaintext rows.
    query = {
        "tenant_id": {"$in": tenant_ids},
        "$or": [
            {"name": rx},
            {"first_name": rx},
            {"last_name": rx},
        ]
        + guest_pii_regex_or_conditions("email", q.strip())
        + guest_pii_regex_or_conditions("phone", q.strip()),
    }
    cursor = db.guests.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "guest_id": 1,
            "tenant_id": 1,
            "name": 1,
            "first_name": 1,
            "last_name": 1,
            "email": 1,
            "phone": 1,
            "loyalty_tier": 1,
        },
    ).limit(limit)

    # Decrypt before the plaintext dedupe key derivation + before returning
    # email/phone, so the cross-property match counter works on plaintext and
    # clients never receive AES envelopes.
    raw = [decrypt_guest_doc(g) async for g in cursor]
    name_map = await _tenant_name_map(tenant_ids)

    # cross-property dedupe: count distinct emails/phones appearing in >1 tenant
    by_key: dict[str, set[str]] = {}
    guests_out: list[dict[str, Any]] = []
    for g in raw:
        gid = g.get("id") or g.get("guest_id")
        full_name = g.get("name") or " ".join(x for x in [g.get("first_name"), g.get("last_name")] if x).strip() or "(isimsiz)"
        email = (g.get("email") or "").lower().strip()
        phone = (g.get("phone") or "").strip()
        key = email or phone
        tid = g.get("tenant_id")
        if key and tid:
            by_key.setdefault(key, set()).add(tid)
        guests_out.append(
            {
                "id": gid,
                "name": full_name,
                "email": g.get("email"),
                "phone": g.get("phone"),
                "tenant_id": tid,
                "property_name": name_map.get(tid, tid),
                "loyalty_tier": g.get("loyalty_tier"),
            }
        )

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

    from security.encrypted_lookup import decrypt_guest_doc, guest_pii_or_conditions

    # email/phone are encrypted at-rest; decrypt the seed before deriving the
    # equality keys, then dual-read (exact blind-index hash + plaintext) so the
    # same person's encrypted records elsewhere in the chain are still located.
    seed = decrypt_guest_doc(seed)
    email = (seed.get("email") or "").strip().lower()
    phone = (seed.get("phone") or "").strip()

    # 2) Locate every guest doc with the same email/phone in the chain
    or_clauses: list[dict[str, Any]] = []
    if email:
        or_clauses += guest_pii_or_conditions("email", email)
    if phone:
        or_clauses += guest_pii_or_conditions("phone", phone)
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
            {"guest_email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}} if email else {"_no_op": True},
        ],
    }
    bookings_cursor = (
        db.bookings.find(
            booking_query,
            {
                "_id": 0,
                "id": 1,
                "tenant_id": 1,
                "check_in": 1,
                "check_out": 1,
                "room_number": 1,
                "room_type": 1,
                "status": 1,
                "total_amount": 1,
                "nights": 1,
            },
        )
        .sort("check_in", -1)
        .limit(200)
    )

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
        stay_history.append(
            {
                "tenant_id": tid,
                "property_name": name_map.get(tid, tid),
                "check_in": b.get("check_in"),
                "check_out": b.get("check_out"),
                "room_number": b.get("room_number"),
                "room_type": b.get("room_type"),
                "status": b.get("status"),
                "total_amount": amt,
                "nights": nights,
            }
        )

    full_name = seed.get("name") or " ".join(x for x in [seed.get("first_name"), seed.get("last_name")] if x).strip()

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
        {
            "$match": {
                "tenant_id": {"$in": tenant_ids},
                "email": {"$nin": [None, ""]},
            }
        },
        {
            "$group": {
                # Group encrypted rows by their deterministic _hash_email blind index
                # (AES-GCM ciphertexts never collide), falling back to lowercased
                # plaintext email for legacy/unmigrated rows.
                "_id": {"$ifNull": ["$_hash_email", {"$toLower": "$email"}]},
                "name": {"$first": "$name"},
                "first_name": {"$first": "$first_name"},
                "last_name": {"$first": "$last_name"},
                "email": {"$first": "$email"},
                "tenants": {"$addToSet": "$tenant_id"},
                "total_records": {"$sum": 1},
                "tier": {"$max": "$loyalty_tier"},
            }
        },
        {"$match": {"$expr": {"$gt": [{"$size": "$tenants"}, 1]}}},
        {
            "$project": {
                "_id": 0,
                "email": 1,
                "name": {
                    "$ifNull": [
                        "$name",
                        {
                            "$concat": [
                                {"$ifNull": ["$first_name", ""]},
                                " ",
                                {"$ifNull": ["$last_name", ""]},
                            ]
                        },
                    ]
                },
                "tier": 1,
                "properties_count": {"$size": "$tenants"},
                "tenants": 1,
                "total_records": 1,
            }
        },
        {"$sort": {"properties_count": -1, "total_records": -1}},
        {"$limit": 100},
    ]

    from security.encrypted_lookup import decrypt_guest_doc

    cursor = db.guests.aggregate(pipeline)
    out: list[dict[str, Any]] = []
    async for row in cursor:
        row = decrypt_guest_doc(row)  # email may be ciphertext from the $group $first
        row["properties"] = [{"tenant_id": t, "name": name_map.get(t, t)} for t in row.pop("tenants", [])]
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
    require_roles(
        current_user,
        {
            UserRole.SUPER_ADMIN,
            UserRole.ADMIN,
            UserRole.SUPERVISOR,
        },
    )

    tenant_ids = await _chain_tenant_ids(current_user)
    primary = await db.guests.find_one(
        {"$or": [{"id": primary_id}, {"guest_id": primary_id}], "tenant_id": {"$in": tenant_ids}},
        {"_id": 1, "tenant_id": 1, "id": 1, "guest_id": 1},
    )
    duplicate = await db.guests.find_one(
        {"$or": [{"id": payload.target_guest_id}, {"guest_id": payload.target_guest_id}], "tenant_id": {"$in": tenant_ids}},
        {"_id": 1, "tenant_id": 1, "id": 1, "guest_id": 1},
    )
    if not primary or not duplicate:
        raise HTTPException(status_code=404, detail="Primary or duplicate guest not found")

    primary_tenant = primary.get("tenant_id")
    dup_tenant = duplicate.get("tenant_id")

    # Canonicalize identifiers — guest docs may carry both `id` and `guest_id`,
    # and dependent records may reference either. Repoint by $in over every
    # known alias of the duplicate, set canonical primary id (prefer guest.id).
    dup_aliases = [v for v in {duplicate.get("id"), duplicate.get("guest_id"), payload.target_guest_id} if v]
    primary_canonical = primary.get("id") or primary.get("guest_id") or primary_id

    repoint_q = {
        "tenant_id": dup_tenant,
        "guest_id": {"$in": dup_aliases},
    }
    booking_res = await db.bookings.update_many(
        repoint_q,
        {"$set": {"guest_id": primary_canonical, "merged_from": payload.target_guest_id}},
    )
    folio_res = await db.folios.update_many(
        repoint_q,
        {"$set": {"guest_id": primary_canonical, "merged_from": payload.target_guest_id}},
    )

    # Safety guard: if linked records exist under any alias but nothing was
    # repointed, abort archive to prevent orphaning.
    expected_bookings = await db.bookings.count_documents({"tenant_id": dup_tenant, "guest_id": {"$in": dup_aliases}})
    expected_folios = await db.folios.count_documents({"tenant_id": dup_tenant, "guest_id": {"$in": dup_aliases}})
    if (expected_bookings > 0 or expected_folios > 0) and booking_res.modified_count == 0 and folio_res.modified_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Repoint produced no updates while linked records exist; aborted",
        )

    # Archive duplicate (soft delete) — pin to the immutable _id we resolved.
    # v109 round-9 IDOR DiD: also assert tenant on the update filter.
    await db.guests.update_one(
        {"_id": duplicate["_id"], "tenant_id": dup_tenant},
        {
            "$set": {
                "archived": True,
                "archived_at": datetime.now(UTC).isoformat(),
                "merged_into": primary_id,
            }
        },
    )

    # Apply optional field overrides on primary — pin to its immutable _id
    if payload.keep_field_overrides:
        safe = {k: v for k, v in payload.keep_field_overrides.items() if k in {"name", "first_name", "last_name", "email", "phone", "loyalty_tier", "preferences", "vip", "company"}}
        if safe:
            # encrypt_guest_update recomputes the plaintext name companions
            # (normalized + merged _ng_name from `primary`) AND encrypts PII
            # fields (email/phone) with their _hash_ tokens before persistence.
            from security.guest_write import encrypt_guest_update

            safe = encrypt_guest_update(safe, primary)
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


# ── v97 Opera-parity: Fuzzy duplicate detection ─────────────────
# Mevcut merge endpoint'i operatör hangi iki kaydı birleştireceğini
# ZATEN biliyor varsayar. Opera Cloud Profile altyapısı ek olarak:
# (a) tüm kayıtları otomatik tarayıp olası duplikat çiftleri puanlar
# (b) tek bir guest için "bu olabilir mi?" candidate listesi sunar
# Bu iki endpoint o boşluğu kapatır. difflib stdlib (rapidfuzz yok).

import difflib as _difflib
from collections import defaultdict as _dd


def _norm_email(e: str | None) -> str:
    return (e or "").strip().lower()


def _norm_phone(p: str | None) -> str:
    if not p:
        return ""
    return "".join(ch for ch in p if ch.isdigit())[-10:]  # son 10 hane


def _full_name(g: dict) -> str:
    n = g.get("name")
    if n:
        return n.strip().lower()
    parts = [g.get("first_name") or "", g.get("last_name") or ""]
    return " ".join(p.strip() for p in parts if p).strip().lower()


def _name_similarity(a: str, b: str) -> float:
    """0..1 arası bayağı eşleşme oranı (SequenceMatcher)."""
    if not a or not b:
        return 0.0
    return _difflib.SequenceMatcher(None, a, b).ratio()


def _score_pair(a: dict, b: dict) -> tuple[float, list[str]]:
    """İki guest doc için duplicate skoru + neden listesi.

    Skorlama (Opera profile match heuristics'a yakın):
      email birebir   → 0.50
      telefon birebir → 0.35
      isim ratio>=.85 → 0.25 * ratio
      isim ratio>=.70 → 0.10 * ratio
    """
    score = 0.0
    reasons: list[str] = []
    ea, eb = _norm_email(a.get("email")), _norm_email(b.get("email"))
    if ea and ea == eb:
        score += 0.50
        reasons.append("email_exact")
    pa, pb = _norm_phone(a.get("phone")), _norm_phone(b.get("phone"))
    if pa and pa == pb:
        score += 0.35
        reasons.append("phone_exact")
    na, nb = _full_name(a), _full_name(b)
    nr = _name_similarity(na, nb)
    if nr >= 0.85:
        score += 0.25 * nr
        reasons.append(f"name_high({nr:.2f})")
    elif nr >= 0.70:
        score += 0.10 * nr
        reasons.append(f"name_medium({nr:.2f})")
    return min(score, 1.0), reasons


@router.get("/duplicates/scan")
@_cached(ttl=600, key_prefix="cross_dup_scan")
async def scan_duplicates(
    min_score: float = Query(0.6, ge=0.3, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_guest_list")),
):
    """Zincir genelinde olası duplikat çiftleri puanla.

    Önce email/phone üzerinde blocking yaparız (CPU optimum), sonra blok
    içindeki her çift için _score_pair hesaplanır. min_score altındakiler
    elenir. Sonuç merge UI'sındaki 'Önerilen birleştirmeler' listesine
    direkt beslenir.
    """
    require_roles(
        current_user,
        {
            UserRole.SUPER_ADMIN,
            UserRole.ADMIN,
            UserRole.SUPERVISOR,
        },
    )
    tenant_ids = await _chain_tenant_ids(current_user)
    name_map = await _tenant_name_map(tenant_ids)

    # 1) Tüm guest'leri tek pass çek (sınırlı projeksiyon, archived hariç)
    cursor = db.guests.find(
        {"tenant_id": {"$in": tenant_ids}, "$or": [{"archived": {"$exists": False}}, {"archived": False}]},
        {"_id": 0, "id": 1, "guest_id": 1, "tenant_id": 1, "name": 1, "first_name": 1, "last_name": 1, "email": 1, "phone": 1, "loyalty_tier": 1},
    ).limit(20000)
    from security.encrypted_lookup import decrypt_guest_doc

    # Decrypt before the _norm_email/_norm_phone blocking + _score_pair + output:
    # AES-GCM ciphertexts differ per row, so bucketing on ciphertext would make
    # the cross-property dedupe blind to every migrated guest.
    all_guests = [decrypt_guest_doc(g) async for g in cursor]

    # 2) Blocking — email + phone son 10 hane bucket'ları
    by_email: dict[str, list[int]] = _dd(list)
    by_phone: dict[str, list[int]] = _dd(list)
    for idx, g in enumerate(all_guests):
        e = _norm_email(g.get("email"))
        p = _norm_phone(g.get("phone"))
        if e:
            by_email[e].append(idx)
        if p:
            by_phone[p].append(idx)

    # 3) Aday çiftleri topla (her bucket içindeki tüm çiftler)
    candidate_pairs: set[tuple[int, int]] = set()
    for buckets in (by_email, by_phone):
        for indices in buckets.values():
            if len(indices) < 2:
                continue
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    a_i, b_i = indices[i], indices[j]
                    if a_i == b_i:
                        continue
                    pair = (a_i, b_i) if a_i < b_i else (b_i, a_i)
                    candidate_pairs.add(pair)

    # 4) Çiftleri puanla, min_score üstündekileri tut
    scored: list[dict[str, Any]] = []
    for i, j in candidate_pairs:
        a, b = all_guests[i], all_guests[j]
        if a.get("tenant_id") == b.get("tenant_id") and (a.get("id") or a.get("guest_id")) == (b.get("id") or b.get("guest_id")):
            continue
        score, reasons = _score_pair(a, b)
        if score < min_score:
            continue
        scored.append(
            {
                "score": round(score, 3),
                "reasons": reasons,
                "cross_property": a.get("tenant_id") != b.get("tenant_id"),
                "left": {
                    "id": a.get("id") or a.get("guest_id"),
                    "tenant_id": a.get("tenant_id"),
                    "property_name": name_map.get(a.get("tenant_id"), a.get("tenant_id")),
                    "name": _full_name(a) or "(isimsiz)",
                    "email": a.get("email"),
                    "phone": a.get("phone"),
                    "loyalty_tier": a.get("loyalty_tier"),
                },
                "right": {
                    "id": b.get("id") or b.get("guest_id"),
                    "tenant_id": b.get("tenant_id"),
                    "property_name": name_map.get(b.get("tenant_id"), b.get("tenant_id")),
                    "name": _full_name(b) or "(isimsiz)",
                    "email": b.get("email"),
                    "phone": b.get("phone"),
                    "loyalty_tier": b.get("loyalty_tier"),
                },
            }
        )

    scored.sort(key=lambda r: r["score"], reverse=True)
    truncated = len(scored) > limit
    return {
        "chain_size": len(tenant_ids),
        "scanned_guests": len(all_guests),
        "candidate_pairs": len(candidate_pairs),
        "matches_count": len(scored),
        "truncated": truncated,
        "min_score": min_score,
        "matches": scored[:limit],
    }


@router.get("/duplicates/suggest/{guest_id}")
async def suggest_duplicates_for(
    guest_id: str,
    min_score: float = Query(0.5, ge=0.3, le=1.0),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_guest_list")),
):
    """Belirli bir misafir için olası duplikat adayları döndür.

    Misafir profil sayfasındaki 'Bu kişi şu kayıtlarla aynı olabilir'
    panelini besler. Aday havuzu önce email/phone bucket'ı, yoksa aynı
    soyad bucket'ı ile sınırlanır.
    """
    tenant_ids = await _chain_tenant_ids(current_user)
    seed = await db.guests.find_one(
        {"$or": [{"id": guest_id}, {"guest_id": guest_id}], "tenant_id": {"$in": tenant_ids}},
        {"_id": 0},
    )
    if not seed:
        raise HTTPException(404, "Misafir zincirde bulunamadı")
    name_map = await _tenant_name_map(tenant_ids)

    from security.encrypted_lookup import decrypt_guest_doc, guest_pii_or_conditions

    # email/phone are encrypted at-rest; decrypt the seed before deriving blocking
    # keys so the candidate query is built from plaintext, not ciphertext.
    seed = decrypt_guest_doc(seed)
    se, sp = _norm_email(seed.get("email")), _norm_phone(seed.get("phone"))
    sl = (seed.get("last_name") or "").strip().lower()

    or_clauses: list[dict[str, Any]] = []
    if se:
        # Exact email matches encrypted candidates via the blind-index hash; the
        # plaintext branch still covers legacy not-yet-backfilled rows. (Phone
        # suffix-matching cannot pre-filter encrypted rows — those are reached via
        # the email/last_name branches and scored on decrypted candidates below.)
        or_clauses += guest_pii_or_conditions("email", se)
    if sp:
        # phone son 10 hane benzerliği için son 7 haneye sufix-match deneriz
        # (tam blocking için dataset taraması gerekir; bu pratik bir yaklaşım)
        suffix = sp[-7:]
        or_clauses.append({"phone": {"$regex": re.escape(suffix)}})
    if sl and len(sl) >= 3:
        or_clauses.append({"last_name": {"$regex": f"^{re.escape(sl)}", "$options": "i"}})
    if not or_clauses:
        return {"seed_id": guest_id, "candidates": [], "checked": 0}

    seed_id = seed.get("id") or seed.get("guest_id")
    cursor = db.guests.find(
        {
            "tenant_id": {"$in": tenant_ids},
            "$or": or_clauses,
            "$and": [
                {"$or": [{"archived": {"$exists": False}}, {"archived": False}]},
            ],
        },
        {"_id": 0, "id": 1, "guest_id": 1, "tenant_id": 1, "name": 1, "first_name": 1, "last_name": 1, "email": 1, "phone": 1, "loyalty_tier": 1},
    ).limit(500)
    candidates_raw = [decrypt_guest_doc(g) async for g in cursor]

    candidates: list[dict[str, Any]] = []
    for c in candidates_raw:
        cid = c.get("id") or c.get("guest_id")
        if cid == seed_id:
            continue
        score, reasons = _score_pair(seed, c)
        if score < min_score:
            continue
        candidates.append(
            {
                "score": round(score, 3),
                "reasons": reasons,
                "cross_property": c.get("tenant_id") != seed.get("tenant_id"),
                "id": cid,
                "tenant_id": c.get("tenant_id"),
                "property_name": name_map.get(c.get("tenant_id"), c.get("tenant_id")),
                "name": _full_name(c) or "(isimsiz)",
                "email": c.get("email"),
                "phone": c.get("phone"),
                "loyalty_tier": c.get("loyalty_tier"),
            }
        )

    candidates.sort(key=lambda r: r["score"], reverse=True)
    return {
        "seed_id": seed_id,
        "seed_name": _full_name(seed),
        "checked": len(candidates_raw),
        "candidates": candidates[:limit],
    }
