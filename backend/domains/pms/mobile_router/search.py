"""
search

Task #333 — Unified cross-entity mobile search for the common shell.

Powers the mobile shell's "Arama" tab. A single query is fanned out across
three EXISTING collections — guests, bookings (reservations) and rooms — and the
matches are returned in one compact, person-centric payload. No new data,
collection or notification type is introduced.

Security:
- Every query is tenant-scoped via the authenticated user (`tenant_id`), so the
  tenant boundary is preserved exactly as in the source search endpoints.
- Guest PII is searched through the encrypted-PII blind-index helper
  (`FieldEncryptionService.build_search_query`) — the raw term is hashed for the
  `_hash_<field>` exact-match path; we never re-expose plaintext PII to the index
  and the unified result deliberately surfaces only the guest's display name +
  VIP flag (no email / phone / id in the list payload).
- Plaintext name / number search uses the index-serviceable `<field>_lower`
  prefix-range helper, matching the source endpoints' behaviour.
- The surface is gated by the `pms` module entitlement, mirroring the guest /
  booking / room search endpoints it federates.
"""
import re as _re

from fastapi import APIRouter, Depends

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from security.search_normalize import prefix_conditions

try:  # pragma: no cover - mirrors pms_guests import guard
    from security.field_encryption import get_field_encryption_service

    _fenc = get_field_encryption_service()
except Exception:  # pragma: no cover
    _fenc = None

router = APIRouter(prefix="/api/mobile/hub", tags=["mobile / hub"])

_GUEST_COLLECTION = "guests"
# Per-entity result caps keep the payload small and the queries cheap.
_PER_ENTITY_LIMIT = 10


def _decrypt_guest(doc: dict) -> dict:
    if _fenc and doc:
        return _fenc.decrypt_document(doc, collection=_GUEST_COLLECTION)
    return doc


async def _search_guests(tenant_id: str, q: str) -> list[dict]:
    """Guest search: plaintext name prefix + encrypted-PII blind index."""
    name_conditions = prefix_conditions(["name", "first_name", "last_name"], q)
    if _fenc:
        # Pass RAW q — build_search_query hashes it for the `_hash_<field>`
        # exact-match index and escapes internally for its regex branch.
        encrypted_conditions = _fenc.build_search_query(
            collection=_GUEST_COLLECTION,
            search_fields=["email", "phone", "id_number", "passport_number"],
            search_value=q,
        )
        or_conditions = name_conditions + encrypted_conditions
    else:
        safe_q = _re.escape(q)
        regex = {"$regex": safe_q, "$options": "i"}
        or_conditions = name_conditions + [
            {"email": regex},
            {"phone": regex},
            {"id_number": regex},
            {"passport_number": regex},
        ]

    if not or_conditions:
        return []

    query = {"tenant_id": tenant_id, "$or": or_conditions}
    raw = (
        await db.guests.find(query, {"_id": 0})
        .sort("name", 1)
        .limit(_PER_ENTITY_LIMIT)
        .to_list(_PER_ENTITY_LIMIT)
    )

    # INFIX (substring) match on the plaintext-name trigram companion `_ng_name`
    # (>= 3 chars), re-verified with a contiguous substring check — mirrors the
    # guest-search endpoint so "type the middle of a name" works here too.
    from security.search_ngram import ngram_all_condition, ngram_match
    ng_cond = ngram_all_condition(q, collection=_GUEST_COLLECTION)
    if ng_cond:
        seen = {g.get("id") for g in raw}
        ng_rows = (
            await db.guests.find({"tenant_id": tenant_id, **ng_cond}, {"_id": 0})
            .sort("name", 1)
            .limit(_PER_ENTITY_LIMIT)
            .to_list(_PER_ENTITY_LIMIT)
        )
        extras = [
            r for r in ng_rows
            if r.get("id") not in seen
            and ngram_match(r, q, collection=_GUEST_COLLECTION)
        ]
        if extras:
            raw = raw + extras
            raw.sort(key=lambda g: (g.get("name") or "").lower())
            raw = raw[:_PER_ENTITY_LIMIT]

    results = []
    for g in raw:
        g = _decrypt_guest(g)
        if "first_name" in g and "last_name" in g:
            name = f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()
        else:
            name = g.get("name") or g.get("email") or "—"
        results.append(
            {
                "id": g.get("id", ""),
                "name": name,
                "vip_status": bool(g.get("vip_status", False)),
            }
        )
    return results


async def _search_reservations(tenant_id: str, q: str) -> list[dict]:
    """Reservation search: index-serviceable prefix on guest_name + booking_number."""
    conds = prefix_conditions(["guest_name", "booking_number"], q)
    if not conds:
        return []
    query = {"tenant_id": tenant_id, "$or": conds}
    raw = (
        await db.bookings.find(
            query,
            {
                "_id": 0,
                "id": 1,
                "booking_number": 1,
                "guest_name": 1,
                "room_number": 1,
                "status": 1,
                "check_in": 1,
                "check_out": 1,
            },
        )
        .sort("created_at", -1)
        .limit(_PER_ENTITY_LIMIT)
        .to_list(_PER_ENTITY_LIMIT)
    )

    def _iso(value) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return [
        {
            "id": b.get("id", ""),
            "booking_number": b.get("booking_number", ""),
            "guest_name": b.get("guest_name", ""),
            "room_number": b.get("room_number"),
            "status": b.get("status", ""),
            "check_in": _iso(b.get("check_in")),
            "check_out": _iso(b.get("check_out")),
        }
        for b in raw
    ]


async def _search_rooms(tenant_id: str, q: str) -> list[dict]:
    """Room search: tenant-scoped anchored prefix on room_number (no PII)."""
    safe_s = _re.escape(q)
    query = {
        "tenant_id": tenant_id,
        "room_number": {"$regex": f"^{safe_s}", "$options": "i"},
    }
    raw = (
        await db.rooms.find(
            query,
            {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "status": 1},
        )
        .sort("room_number", 1)
        .limit(_PER_ENTITY_LIMIT)
        .to_list(_PER_ENTITY_LIMIT)
    )
    return [
        {
            "id": r.get("id", ""),
            "room_number": r.get("room_number", ""),
            "room_type": r.get("room_type", ""),
            "status": r.get("status", ""),
        }
        for r in raw
        if not r.get("is_virtual")
    ]


@router.get("/search")
async def unified_search(
    q: str = "",
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Cross-entity search over guests, reservations and rooms.

    Returns at most `_PER_ENTITY_LIMIT` matches per entity. A query shorter than
    2 characters returns empty groups (DoS / noise guard), matching the source
    guest-search endpoint.
    """
    # Strip null bytes (MongoDB regex rejects them) and clamp length.
    q = (q or "").replace("\x00", "").strip()
    if len(q) < 2:
        return {
            "query": q,
            "guests": [],
            "reservations": [],
            "rooms": [],
            "total": 0,
        }
    if len(q) > 200:
        q = q[:200]

    tenant_id = current_user.tenant_id
    guests = await _search_guests(tenant_id, q)
    reservations = await _search_reservations(tenant_id, q)
    rooms = await _search_rooms(tenant_id, q)

    return {
        "query": q,
        "guests": guests,
        "reservations": reservations,
        "rooms": rooms,
        "total": len(guests) + len(reservations) + len(rooms),
    }
