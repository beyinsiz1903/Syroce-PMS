"""Public web-booking engine backed by the hotel's real PMS inventory."""

import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.atomic_booking import BookingConflictError, create_booking_atomic, release_booking_nights
from core.database import db
from core.utils import generate_folio_number
from models.schemas import Folio, FolioType
from security.guest_write import encrypt_guest_insert

router = APIRouter(prefix="/api/wbe", tags=["WBE Public"])
logger = logging.getLogger("routers.wbe_public")

ACTIVE_STATUSES = ["confirmed", "guaranteed", "checked_in", "pending"]
UNSELLABLE_ROOM_STATUSES = {"maintenance", "out_of_order", "out_of_service", "blocked"}


class RoomAvailabilityOut(BaseModel):
    room_type_id: str
    name: str
    description: str = ""
    capacity: int
    available_count: int
    price_per_night: float
    total_price: float
    currency: str = "TRY"
    image_url: str | None = None
    amenities: list[str] = Field(default_factory=list)


class WBEBookingRequest(BaseModel):
    room_type_id: str
    check_in: date
    check_out: date
    adults: int = Field(1, ge=1, le=20)
    children: int = Field(0, ge=0, le=20)
    guest_name: str = Field(min_length=2, max_length=160)
    guest_email: str = Field(min_length=3, max_length=254)
    guest_phone: str = Field(min_length=5, max_length=40)
    special_requests: str | None = Field(None, max_length=1000)


class WBEBookingResponse(BaseModel):
    booking_id: str
    confirmation_number: str
    status: str
    total_price: float
    currency: str = "TRY"


def _stay_bounds(check_in: date, check_out: date) -> tuple[str, str, int]:
    if check_in >= check_out:
        raise HTTPException(status_code=400, detail="Çıkış tarihi giriş tarihinden sonra olmalıdır.")
    return f"{check_in.isoformat()}T00:00:00", f"{check_out.isoformat()}T00:00:00", (check_out - check_in).days


async def _public_tenant(tenant_id: str) -> dict:
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    modules = (tenant or {}).get("modules") or {}
    if not tenant or modules.get("booking_engine") is False or tenant.get("subscription_status") not in {None, "active", "trial"}:
        raise HTTPException(status_code=404, detail="Rezervasyon sayfası kullanıma açık değil.")
    return tenant


async def _sellable_rooms(tenant_id: str, room_type: str | None = None) -> list[dict]:
    query = {"tenant_id": tenant_id}
    if room_type:
        query["room_type"] = room_type
    rooms = await db.rooms.find(query, {"_id": 0}).to_list(2000)
    return [
        room for room in rooms
        if room.get("is_active") is not False
        and str(room.get("status") or "").lower() not in UNSELLABLE_ROOM_STATUSES
    ]


async def _has_conflict(tenant_id: str, room_id: str, start: str, end: str) -> bool:
    return bool(await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "room_id": room_id,
        "status": {"$in": ACTIVE_STATUSES},
        "check_in": {"$lt": end},
        "check_out": {"$gt": start},
    }))


@router.get("/{tenant_id}/availability", response_model=list[RoomAvailabilityOut])
async def get_availability(tenant_id: str, check_in: date, check_out: date, adults: int = 1, children: int = 0):
    start, end, nights = _stay_bounds(check_in, check_out)
    if adults < 1 or children < 0 or adults + children > 20:
        raise HTTPException(status_code=400, detail="Misafir sayısı geçersiz.")
    tenant = await _public_tenant(tenant_id)
    currency = tenant.get("currency") or "TRY"
    party_size = adults + children
    grouped: dict[str, dict] = {}

    for room in await _sellable_rooms(tenant_id):
        capacity = int(room.get("capacity") or 2)
        price = float(room.get("base_price") or 0)
        if capacity < party_size or price <= 0:
            continue
        room_type = str(room.get("room_type") or "Standart")
        entry = grouped.setdefault(room_type, {
            "room_type_id": room_type,
            "name": room.get("room_type_display_name") or room_type,
            "description": room.get("description") or "",
            "capacity": capacity,
            "available_count": 0,
            "price_per_night": price,
            "currency": currency,
            "image_url": room.get("image_url") or (room.get("images") or [None])[0],
            "amenities": room.get("amenities") or [],
        })
        entry["capacity"] = max(entry["capacity"], capacity)
        entry["price_per_night"] = min(entry["price_per_night"], price)
        if not await _has_conflict(tenant_id, room.get("id"), start, end):
            entry["available_count"] += 1

    return [
        RoomAvailabilityOut(**entry, total_price=round(entry["price_per_night"] * nights, 2))
        for entry in grouped.values() if entry["available_count"] > 0
    ]


@router.post("/{tenant_id}/book", response_model=WBEBookingResponse)
async def create_booking(tenant_id: str, req: WBEBookingRequest):
    start, end, nights = _stay_bounds(req.check_in, req.check_out)
    tenant = await _public_tenant(tenant_id)
    rooms = [room for room in await _sellable_rooms(tenant_id, req.room_type_id)
             if int(room.get("capacity") or 2) >= req.adults + req.children and float(room.get("base_price") or 0) > 0]
    if not rooms:
        raise HTTPException(status_code=404, detail="Seçilen oda tipi satışa açık değil.")

    selected = None
    for room in rooms:
        if not await _has_conflict(tenant_id, room.get("id"), start, end):
            selected = room
            break
    if not selected:
        raise HTTPException(status_code=409, detail="Seçilen tarihler için müsait oda kalmadı.")

    unit_price = min(float(room.get("base_price") or 0) for room in rooms)
    total_price = round(unit_price * nights, 2)
    currency = tenant.get("currency") or "TRY"
    guest_id = str(uuid.uuid4())
    booking_id = str(uuid.uuid4())
    confirmation = f"WEB-{datetime.now(UTC).strftime('%y%m%d')}-{booking_id[:6].upper()}"
    now = datetime.now(UTC).isoformat()
    guest_doc = encrypt_guest_insert({
        "id": guest_id,
        "tenant_id": tenant_id,
        "name": req.guest_name.strip(),
        "email": req.guest_email.strip().lower(),
        "phone": req.guest_phone.strip(),
        "created_at": now,
    })
    booking_doc = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "guest_id": guest_id,
        "guest_name": req.guest_name.strip(),
        "guest_email": req.guest_email.strip().lower(),
        "guest_phone": req.guest_phone.strip(),
        "room_id": selected.get("id"),
        "room_number": selected.get("room_number") or "",
        "room_type": req.room_type_id,
        "check_in": f"{req.check_in.isoformat()}T14:00:00",
        "check_out": f"{req.check_out.isoformat()}T11:00:00",
        "adults": req.adults,
        "children": req.children,
        "guests_count": req.adults + req.children,
        "status": "pending",
        "payment_status": "pending",
        "total_amount": total_price,
        "balance": total_price,
        "currency": currency,
        "channel": "web",
        "source_channel": "web_booking_engine",
        "origin": "wbe",
        "confirmation_code": confirmation,
        "special_requests": req.special_requests,
        "created_at": now,
        "updated_at": now,
    }

    await db.guests.insert_one(guest_doc)
    try:
        await create_booking_atomic(tenant_id=tenant_id, booking_doc=booking_doc)
    except BookingConflictError as exc:
        await db.guests.delete_one({"id": guest_id, "tenant_id": tenant_id})
        raise HTTPException(status_code=409, detail="Oda az önce başka bir rezervasyona ayrıldı; lütfen yeniden arayın.") from exc
    except Exception:
        await db.guests.delete_one({"id": guest_id, "tenant_id": tenant_id})
        raise

    try:
        folio = Folio(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            booking_id=booking_id,
            folio_number=await generate_folio_number(tenant_id),
            folio_type=FolioType.GUEST,
            guest_id=guest_id,
        )
        await db.folios.insert_one(folio.model_dump(mode="json"))
    except Exception:
        # A public booking without a folio is not operationally usable. Release
        # the atomic room-night claim before deleting its owner record.
        await release_booking_nights(tenant_id, booking_id, reason="wbe_folio_create_failed")
        await db.bookings.delete_one({"id": booking_id, "tenant_id": tenant_id})
        await db.guests.delete_one({"id": guest_id, "tenant_id": tenant_id})
        raise

    try:
        await db.audit_logs.insert_one({
            "tenant_id": tenant_id,
            "action": "wbe_booking_created",
            "target_id": booking_id,
            "details": {"confirmation": confirmation, "room_type": req.room_type_id},
            "created_at": now,
        })
    except Exception:
        # The booking has already committed atomically. Do not ask the guest to
        # retry and create a duplicate merely because observability is degraded.
        logger.exception("WBE audit write failed tenant=%s booking=%s", tenant_id, booking_id)

    return WBEBookingResponse(
        booking_id=booking_id,
        confirmation_number=confirmation,
        status="pending",
        total_price=total_price,
        currency=currency,
    )
