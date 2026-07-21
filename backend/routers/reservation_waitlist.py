"""
PMS / Reservation Waitlist Domain Router (Task #169 / KOVA 4)

Reservation-level waitlist surface. This is DISTINCT from the spa waitlist
(`/api/spa/waitlist` in `domains/spa/router.py`); that module handles
appointment waitlisting and is out of scope here.

Product gap addressed: when a guest cannot be booked immediately (no
availability for the desired room type / dates), staff add them to a
reservation waitlist. Once a room frees up, an entry is *promoted* into a
real confirmed booking (atomic room-night locking via `create_booking_atomic`).

Tenant scope + RBAC:
  - All routes are tenant-scoped (every query pins `tenant_id`).
  - add / list / delete require `require_module("pms")`.
  - promote additionally requires `require_op("manage_sales")` because it
    creates a booking (mutating, revenue-affecting surface).
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module, require_op

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/waitlist", tags=["PMS / Reservation Waitlist"])

_PRIORITIES = {"low", "normal", "high", "vip"}
_ACTIVE_STATUSES = ["waiting", "notified"]


class ReservationWaitlistIn(BaseModel):
    guest_name: str
    room_type: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guest_email: str | None = None
    guest_phone: str | None = None
    guest_id: str | None = None
    adults: int = 1
    children: int = 0
    preferred_rate: float | None = None
    priority: str = "normal"
    notes: str | None = None


class WaitlistPromoteIn(BaseModel):
    # Optional explicit room; if omitted, the first available room of the
    # waitlist entry's room_type is selected.
    room_id: str | None = None
    total_amount: float | None = None


def _parse_date(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Geçersiz {label} tarih formatı")


@router.get("")
async def list_waitlist(
    status: str | None = Query(None),
    room_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module("pms")),
) -> dict:
    """List reservation waitlist entries for the caller's tenant."""
    q: dict = {"tenant_id": current_user.tenant_id}
    q["status"] = status if status else {"$in": _ACTIVE_STATUSES}
    if room_type:
        q["room_type"] = room_type
    cur = db.reservation_waitlist.find(q, {"_id": 0}).sort("created_at", 1).limit(200)
    entries = [d async for d in cur]
    return {"waitlist": entries, "total_count": len(entries)}


@router.post("")
async def add_to_waitlist(
    body: ReservationWaitlistIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module("pms")),
) -> dict:
    """Add a guest to the reservation waitlist."""
    if not body.guest_name.strip():
        raise HTTPException(status_code=400, detail="Misafir adı boş olamaz")
    if not body.room_type.strip():
        raise HTTPException(status_code=400, detail="Oda tipi boş olamaz")
    ci = _parse_date(body.check_in, "giriş")
    co = _parse_date(body.check_out, "çıkış")
    if co <= ci:
        raise HTTPException(status_code=400, detail="Çıkış tarihi girişten sonra olmalıdır")
    if body.priority not in _PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Geçersiz öncelik: {body.priority}")

    now = datetime.now(UTC)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(),
        "guest_name": body.guest_name.strip(),
        "room_type": body.room_type.strip(),
        "status": "waiting",
        "booking_id": None,
        "created_at": now.isoformat(),
        "created_by": current_user.id,
    }
    await db.reservation_waitlist.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/{entry_id}/promote")
async def promote_waitlist_entry(
    entry_id: str,
    body: WaitlistPromoteIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module("pms")),
    _perm_op=Depends(require_op("manage_sales")),
) -> dict:
    """Promote a waitlist entry into a confirmed booking.

    Picks the requested room (or the first available room of the entry's
    room_type), repoints/creates the guest record, and creates the booking
    atomically. Returns 409 if no room is available or a room-night conflict
    occurs (expected guard behaviour).
    """
    tenant_id = current_user.tenant_id
    entry = await db.reservation_waitlist.find_one({"id": entry_id, "tenant_id": tenant_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Bekleme listesi kaydı bulunamadı")
    if entry.get("status") == "promoted":
        raise HTTPException(status_code=409, detail="Kayıt zaten rezervasyona dönüştürülmüş")
    if entry.get("status") == "cancelled":
        raise HTTPException(status_code=409, detail="İptal edilmiş kayıt promote edilemez")

    # Resolve target room (tenant-scoped).
    if body.room_id:
        room = await db.rooms.find_one({"id": body.room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            raise HTTPException(status_code=404, detail="Oda bulunamadı")
    else:
        room = await db.rooms.find_one({"tenant_id": tenant_id, "room_type": entry.get("room_type"), "status": "available"}, {"_id": 0})
        if not room:
            raise HTTPException(status_code=409, detail=f"{entry.get('room_type')} tipinde uygun oda yok — promote edilemedi")

    # Resolve / create guest (tenant-scoped).
    guest_id = entry.get("guest_id")
    if guest_id:
        existing = await db.guests.find_one({"id": guest_id, "tenant_id": tenant_id}, {"_id": 0})
        if not existing:
            guest_id = None
    if not guest_id:
        guest_id = str(uuid.uuid4())
        from security.guest_write import encrypt_guest_insert

        await db.guests.insert_one(
            encrypt_guest_insert(
                {
                    "id": guest_id,
                    "tenant_id": tenant_id,
                    "name": entry.get("guest_name"),
                    "email": entry.get("guest_email") or f"waitlist-{guest_id[:8]}@placeholder.local",
                    "phone": entry.get("guest_phone") or "",
                    "id_number": "",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
        )

    now = datetime.now(UTC)
    booking = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "guest_id": guest_id,
        "room_id": room["id"],
        "check_in": entry.get("check_in"),
        "check_out": entry.get("check_out"),
        "status": "confirmed",
        "adults": int(entry.get("adults") or 1),
        "children": int(entry.get("children") or 0),
        "total_amount": (body.total_amount if body.total_amount is not None else float(entry.get("preferred_rate") or 0.0)),
        "rate_type": "waitlist_promote",
        "market_segment": "direct",
        "channel": "direct",
        "source_channel": "direct",
        "promoted_from_waitlist": entry_id,
        "created_at": now.isoformat(),
        "created_by": current_user.id,
    }
    from core.atomic_booking import BookingConflictError, create_booking_atomic

    try:
        await create_booking_atomic(tenant_id=tenant_id, booking_doc=booking)
    except BookingConflictError as exc:
        raise HTTPException(status_code=409, detail=f"Oda çakışması: {exc}")

    await db.reservation_waitlist.update_one(
        {"id": entry_id, "tenant_id": tenant_id},
        {
            "$set": {
                "status": "promoted",
                "booking_id": booking["id"],
                "room_id": room["id"],
                "promoted_at": now.isoformat(),
                "promoted_by": current_user.id,
            }
        },
    )
    return {
        "success": True,
        "entry_id": entry_id,
        "booking_id": booking["id"],
        "room_id": room["id"],
        "guest_id": guest_id,
        "status": "promoted",
    }


@router.delete("/{entry_id}")
async def remove_waitlist_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module("pms")),
) -> dict:
    """Remove a reservation waitlist entry (tenant-scoped)."""
    res = await db.reservation_waitlist.delete_one({"id": entry_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Bekleme listesi kaydı bulunamadı")
    return {"ok": True, "deleted": entry_id}
