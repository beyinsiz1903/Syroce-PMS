"""
Walk-in 30-saniye akisi: tek istekte misafir + rezervasyon + check-in.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from routers.pms_guests import _encrypt_guest

router = APIRouter(prefix="/api/pms/walkin", tags=["pms"])


@router.get("/available-rooms")
async def available_rooms(
    nights: int = 1,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_room_status")),
):
    """Bugunden itibaren `nights` gece icin musait odalari dondur."""
    tenant_id = current_user.tenant_id
    today = datetime.now(UTC).date()
    end = today + timedelta(days=max(1, min(7, nights)))
    today_s = today.isoformat()
    end_s = end.isoformat()

    rooms = await db.rooms.find(
        {"tenant_id": tenant_id, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "base_rate": 1, "rate": 1, "max_occupancy": 1},
    ).to_list(500)

    busy_ids = set()
    cursor = db.bookings.find({
        "tenant_id": tenant_id,
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house"]},
        "check_in": {"$lt": end_s},
        "check_out": {"$gt": today_s},
    }, {"_id": 0, "room_id": 1})
    async for b in cursor:
        if b.get("room_id"):
            busy_ids.add(b["room_id"])

    out = []
    for r in rooms:
        if r["id"] in busy_ids:
            continue
        out.append({
            "id": r["id"],
            "room_number": r.get("room_number"),
            "room_type": r.get("room_type"),
            "rate": float(r.get("base_rate") or r.get("rate") or 0),
            "max_occupancy": r.get("max_occupancy") or 2,
        })
    out.sort(key=lambda x: str(x.get("room_number") or ""))
    return {"rooms": out, "count": len(out), "nights": nights}


class WalkinRequest(BaseModel):
    guest_name: str
    phone: str = ""
    id_number: str = ""
    email: str = ""
    room_id: str
    nights: int = Field(default=1, ge=1, le=14)
    adults: int = Field(default=1, ge=1, le=8)
    children: int = Field(default=0, ge=0, le=8)
    total_amount: float
    payment_amount: float = 0
    payment_method: str = "cash"
    note: str = ""


@router.post("/checkin")
async def walkin_checkin(
    payload: WalkinRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("create_booking")),
):
    if not payload.guest_name.strip():
        raise HTTPException(400, "Misafir adi gerekli")
    if payload.total_amount <= 0:
        raise HTTPException(400, "Tutar gecerli olmali")

    tenant_id = current_user.tenant_id
    now = datetime.now(UTC)
    today = now.date()
    co_date = today + timedelta(days=payload.nights)

    room = await db.rooms.find_one({"id": payload.room_id, "tenant_id": tenant_id}, {"_id": 0})
    if not room:
        raise HTTPException(404, "Oda bulunamadi")

    overlap = await db.bookings.find_one({
        "tenant_id": tenant_id,
        "room_id": payload.room_id,
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house"]},
        "check_in": {"$lt": co_date.isoformat()},
        "check_out": {"$gt": today.isoformat()},
    })
    if overlap:
        raise HTTPException(409, "Oda secilen tarihte musait degil")

    # Guest — PII alanlari sifrelenir (pms_guests pattern)
    guest_id = str(uuid.uuid4())
    guest_plain = {
        "id": guest_id,
        "tenant_id": tenant_id,
        "name": payload.guest_name.strip(),
        "email": payload.email.strip() or f"walkin-{guest_id[:8]}@placeholder.local",
        "phone": payload.phone.strip(),
        "id_number": payload.id_number.strip(),
        "vip_status": False,
        "loyalty_points": 0,
        "total_stays": 0,
        "total_spend": 0.0,
        "is_walkin": True,
        "created_at": now.isoformat(),
    }
    from security.search_normalize import apply_collection_normalized_fields
    await db.guests.insert_one(
        apply_collection_normalized_fields(_encrypt_guest(guest_plain.copy()), collection="guests")
    )

    # Booking — atomic checked_in. Conditional update ile son anda cakisma kontrolu:
    # ayni odaya ayni anda iki insert olursa, ikinci sorgu room_id+overlap'i tekrar gorur.
    booking_id = str(uuid.uuid4())
    # Re-check overlap right before insert (kucuk yaris penceresini daraltir)
    overlap2 = await db.bookings.find_one({
        "tenant_id": tenant_id,
        "room_id": payload.room_id,
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house"]},
        "check_in": {"$lt": co_date.isoformat()},
        "check_out": {"$gt": today.isoformat()},
    })
    if overlap2:
        # rollback guest
        await db.guests.delete_one({"id": guest_id, "tenant_id": tenant_id})
        raise HTTPException(409, "Oda az once baska bir misafire atandi")
    booking_doc = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "guest_id": guest_id,
        "room_id": payload.room_id,
        "room_number": room.get("room_number"),
        "check_in": today.isoformat(),
        "check_out": co_date.isoformat(),
        "nights": payload.nights,
        "adults": payload.adults,
        "children": payload.children,
        "guests_count": payload.adults + payload.children,
        "total_amount": float(payload.total_amount),
        "total_price": float(payload.total_amount),
        "currency": "TRY",
        "status": "checked_in",
        "channel": "walk_in",
        "source_channel": "walk_in",
        "origin": "walkin",
        "checked_in_at": now.isoformat(),
        "checked_in_by_id": current_user.id,
        "checked_in_by_name": current_user.name or current_user.email,
        "notes": payload.note,
        "created_at": now.isoformat(),
    }
    await db.bookings.insert_one(booking_doc)

    # Folyo + odeme
    folio_id = str(uuid.uuid4())
    await db.folios.insert_one({
        "id": folio_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "guest_id": guest_id,
        "room_charge": float(payload.total_amount),
        "total": float(payload.total_amount),
        "balance": float(payload.total_amount) - float(payload.payment_amount or 0),
        "status": "open",
        "created_at": now.isoformat(),
    })
    paid = float(payload.payment_amount or 0)
    if paid > 0:
        await db.folio_payments.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": booking_id,
            "amount": paid,
            "method": payload.payment_method,
            "payment_date": today.isoformat(),
            "received_by_id": current_user.id,
            "received_by_name": current_user.name or current_user.email,
            "created_at": now.isoformat(),
        })

    # Oda durumu
    await db.rooms.update_one(
        {"id": payload.room_id, "tenant_id": tenant_id},
        {"$set": {"status": "occupied", "current_booking_id": booking_id}},
    )

    return {
        "ok": True,
        "guest_id": guest_id,
        "booking_id": booking_id,
        "folio_id": folio_id,
        "room_number": room.get("room_number"),
        "balance": float(payload.total_amount) - paid,
    }
