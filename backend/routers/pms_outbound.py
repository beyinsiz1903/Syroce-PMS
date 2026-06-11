"""Outbound PMS API consumed by Af-sadakat (and other paying integrations).

All endpoints authenticated by tenant API key (Bearer). The API key is
issued during marketplace activation by the Af-sadakat provisioner.

This is the read-only PMS surface Af-sadakat needs:
- rooms list (for guest panels & QR)
- reservations (active / window) — for sync
- guests (lookup by reservation/room)
- folio.charge — push a charge from Af-sadakat into PMS folio
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import (
    APIRouter,
    Depends,  # v92 DW
    Header,
    HTTPException,
    Query,
)
from pydantic import BaseModel, Field

from core.afsadakat_provisioner import (
    AFSADAKAT_PRODUCT_KEY,
    find_tenant_by_api_key,
)
from core.subscriptions import tenant_has_module
from modules.pms_core.role_permission_service import require_op  # v92 DW

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pms-outbound", tags=["pms-outbound"])


def _db():
    from core.database import _raw_db
    return _raw_db


async def _auth(authorization: str | None) -> dict[str, Any]:
    """Validate API key AND that the tenant still has an active
    Af-sadakat entitlement. This closes the lifecycle loophole: when a
    subscription expires/cancels, outbound access is denied immediately
    even if the credential row stays in the integrations collection."""
    api_key = ""
    if authorization and authorization.lower().startswith("bearer "):
        api_key = authorization.split(" ", 1)[1].strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    creds = await find_tenant_by_api_key(api_key)
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid API key")
    entitled = await tenant_has_module(creds["tenant_id"], AFSADAKAT_PRODUCT_KEY)
    if not entitled:
        # 403 — credential is recognized but subscription is no longer
        # active. Caller should stop polling and prompt the hotelier
        # to renew via the marketplace.
        raise HTTPException(
            status_code=403,
            detail="Af-sadakat aboneliği aktif değil — entegrasyon askıda"
        )
    return creds


def _strip_id(doc: dict) -> dict:
    if not isinstance(doc, dict):
        return doc
    doc.pop("_id", None)
    return doc


# ── Rooms ────────────────────────────────────────────────────────
@router.get("/rooms")
async def list_rooms(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=500, le=2000),
) -> dict:
    creds = await _auth(authorization)
    tenant_id = creds["tenant_id"]
    db = _db()
    cur = db.rooms.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1,
         "status": 1, "floor": 1, "capacity": 1},
    ).limit(limit)
    items = [_strip_id(d) async for d in cur]
    return {"rooms": items, "count": len(items)}


# ── Reservations ─────────────────────────────────────────────────
@router.get("/reservations")
async def list_reservations(
    authorization: str | None = Header(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
) -> dict:
    creds = await _auth(authorization)
    tenant_id = creds["tenant_id"]
    db = _db()
    q: dict[str, Any] = {"tenant_id": tenant_id}
    if status:
        q["status"] = status
    cur = db.reservations.find(
        q,
        {"_id": 0, "id": 1, "guest_id": 1, "guest_name": 1,
         "room_number": 1, "check_in": 1, "check_out": 1,
         "status": 1, "adults": 1, "children": 1, "total": 1},
    ).sort("check_in", -1).limit(limit)
    items = [_strip_id(d) async for d in cur]
    return {"reservations": items, "count": len(items)}


@router.get("/reservations/{reservation_id}")
async def get_reservation(
    reservation_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    creds = await _auth(authorization)
    db = _db()
    doc = await db.reservations.find_one(
        {"id": reservation_id, "tenant_id": creds["tenant_id"]},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    return doc


# ── Guests ───────────────────────────────────────────────────────
@router.get("/guests")
async def list_guests(
    authorization: str | None = Header(default=None),
    q: str | None = Query(default=None, description="ad/soyad/email arama"),
    limit: int = Query(default=100, le=500),
) -> dict:
    creds = await _auth(authorization)
    tenant_id = creds["tenant_id"]
    db = _db()
    flt: dict[str, Any] = {"tenant_id": tenant_id}
    if q:
        from security.query_safety import safe_search_term
        if (_s := safe_search_term(q)):
            flt["$or"] = [
                {"first_name": {"$regex": _s, "$options": "i"}},
                {"last_name": {"$regex": _s, "$options": "i"}},
                {"email": {"$regex": _s, "$options": "i"}},
            ]
    cur = db.guests.find(
        flt,
        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1,
         "email": 1, "phone": 1, "loyalty_id": 1, "vip": 1},
    ).limit(limit)
    from security.encrypted_lookup import decrypt_guest_doc
    items = [decrypt_guest_doc(_strip_id(d)) async for d in cur]
    return {"guests": items, "count": len(items)}


@router.get("/guests/{guest_id}")
async def get_guest(
    guest_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    creds = await _auth(authorization)
    db = _db()
    from security.encrypted_lookup import decrypt_guest_doc
    doc = decrypt_guest_doc(await db.guests.find_one(
        {"id": guest_id, "tenant_id": creds["tenant_id"]},
        {"_id": 0},
    ))
    if not doc:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    return doc


# ── Folio charge push ────────────────────────────────────────────
class FolioChargeIn(BaseModel):
    reservation_id: str
    description: str
    amount: float = Field(gt=0)
    currency: str = "TRY"
    source: str = Field(default="afsadakat",
                        description="Af-sadakat module that originated the charge")
    external_ref: str | None = None  # idempotency key from caller


@router.post("/folio/charge")
async def post_folio_charge(
    payload: FolioChargeIn,
    authorization: str | None = Header(default=None),
    _perm=Depends(require_op("post_charge")),  # v92 DW
) -> dict:
    """Append a charge to a reservation folio. Idempotent on external_ref."""
    creds = await _auth(authorization)
    tenant_id = creds["tenant_id"]
    db = _db()
    res = await db.reservations.find_one(
        {"id": payload.reservation_id, "tenant_id": tenant_id},
        {"_id": 0, "id": 1},
    )
    if not res:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    import uuid
    from datetime import UTC, datetime

    from pymongo.errors import DuplicateKeyError
    charge_id = str(uuid.uuid4())
    doc = {
        "id": charge_id,
        "tenant_id": tenant_id,
        "reservation_id": payload.reservation_id,
        "description": payload.description,
        "amount": float(payload.amount),
        "currency": payload.currency,
        "source": payload.source,
        "external_ref": payload.external_ref,
        "created_at": datetime.now(UTC).isoformat(),
    }
    # Atomic idempotency: rely on the unique partial index over
    # (tenant_id, source, external_ref) to make concurrent inserts with
    # the same external_ref fail-fast. On duplicate, look the existing
    # charge up and return it — no double-charge race.
    try:
        await db.folio_charges.insert_one(doc)
    except DuplicateKeyError:
        existing = await db.folio_charges.find_one({
            "tenant_id": tenant_id,
            "source": payload.source,
            "external_ref": payload.external_ref,
        }, {"_id": 0, "id": 1})
        if existing:
            return {"ok": True, "charge_id": existing["id"], "duplicate": True}
        # Index hit but doc not found → race against deletion; rethrow
        raise
    logger.info("[pms-outbound] tenant=%s folio charge %s amount=%s source=%s",
                tenant_id, charge_id, payload.amount, payload.source)
    return {"ok": True, "charge_id": charge_id, "duplicate": False}
