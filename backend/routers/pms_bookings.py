"""
PMS Bookings Router — Extracted from routers/pms.py (Stage 2 decomposition)
Booking CRUD, approval/rejection, multi-room bookings, room move history.
"""
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from core.database import db
from core.helpers import create_audit_log, require_module
from core.security import get_current_user
from core.utils import generate_folio_number, generate_qr_code, generate_time_based_qr_token

try:
    from security.encrypted_lookup import decrypt_booking_doc
    _decrypt_booking = decrypt_booking_doc
except Exception:
    def _decrypt_booking(doc):
        return doc
from models.enums import (
    BookingStatus,
    CancellationPolicyType,
    ChannelType,
    ContractedRateType,
    FolioType,
    MarketSegment,
    RateType,
)
from models.schemas import (
    Booking,
    BookingCreate,
    Folio,
    Guest,
    GuestCreate,
    RateOverrideLog,
    User,
    _ensure_hotel_context,
)
from modules.reservations.services.create_reservation_service import CreateReservationService
from modules.reservations.services.reservation_read_service import ReservationReadService
from modules.reservations.services.update_reservation_service import UpdateReservationService

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["pms"])
security = HTTPBearer()

create_reservation_service = CreateReservationService()
reservation_read_service = ReservationReadService()
update_reservation_service = UpdateReservationService()

REJECTED_STATUS = "rejected"

# ── Local models ──

RejectReasonCode = Literal[
    "NO_AVAILABILITY", "PRICE_MISMATCH", "OVERBOOK", "POLICY", "OTHER",
]


class RejectRequest(BaseModel):
    reason_code: RejectReasonCode
    reason_note: str | None = Field(default=None, max_length=500)


class QuickBookingCreate(BaseModel):
    guest_name: str
    room_id: str
    check_in: str
    check_out: str
    total_amount: float
    guest_id: str | None = None


class MultiRoomBookingCreate(BaseModel):
    guest_id: str | None = None
    guest: GuestCreate | None = None
    arrival_date: str
    departure_date: str
    rooms: list[dict]
    company_id: str | None = None
    channel: ChannelType = ChannelType.DIRECT
    special_requests: str | None = None
    contracted_rate: ContractedRateType | None = None
    rate_type: RateType | None = None
    market_segment: MarketSegment | None = None
    cancellation_policy: CancellationPolicyType | None = None
    billing_address: str | None = None
    billing_tax_number: str | None = None
    billing_contact_person: str | None = None


# ── Routes ──


@router.post("/pms/bookings")
async def create_booking(
    booking_data: BookingCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    return await create_reservation_service.create(booking_data, current_user, request)


@router.post("/pms/quick-booking")
async def create_quick_booking(
    data: QuickBookingCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Hizli rezervasyon: misafir adi + oda + tarih + fiyat ile tek adimda rezervasyon olustur."""
    tenant_id = current_user.tenant_id

    # Validate inputs
    if not data.guest_name.strip():
        raise HTTPException(status_code=400, detail="Misafir adi bos olamaz")
    if data.total_amount <= 0:
        raise HTTPException(status_code=400, detail="Gecerli bir fiyat giriniz")

    ci_dt = datetime.fromisoformat(data.check_in.replace('Z', '+00:00'))
    co_dt = datetime.fromisoformat(data.check_out.replace('Z', '+00:00'))
    if co_dt <= ci_dt:
        raise HTTPException(status_code=400, detail="Cikis tarihi giristen sonra olmalidir")

    # 1) Validate room exists
    room = await db.rooms.find_one({"id": data.room_id, "tenant_id": tenant_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadi")

    # 2) Use existing guest or create new one
    if data.guest_id:
        existing_guest = await db.guests.find_one(
            {"id": data.guest_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not existing_guest:
            raise HTTPException(status_code=404, detail="Secilen misafir bulunamadi")
        guest_id = data.guest_id
    else:
        guest_id = str(uuid.uuid4())
        now_ts = datetime.now(UTC)
        guest_doc = {
            "id": guest_id,
            "tenant_id": tenant_id,
            "name": data.guest_name.strip(),
            "email": f"walk-in-{guest_id[:8]}@placeholder.local",
            "phone": "",
            "id_number": "",
            "vip_status": False,
            "loyalty_points": 0,
            "total_stays": 0,
            "total_spend": 0.0,
            "created_at": now_ts.isoformat(),
        }
        await db.guests.insert_one(guest_doc)

    # 3) Build BookingCreate and delegate to the standard service
    booking_data = BookingCreate(
        guest_id=guest_id,
        room_id=data.room_id,
        check_in=data.check_in,
        check_out=data.check_out,
        adults=1,
        children=0,
        guests_count=1,
        total_amount=data.total_amount,
        channel="direct",
        source_channel="direct",
        origin="ui",
    )
    result = await create_reservation_service.create(booking_data, current_user, request)
    result["guest_name"] = data.guest_name.strip()
    result["room_number"] = room.get("room_number")
    return result


@router.get("/pms/bookings")
async def get_bookings(
    limit: int = 30,  # Further reduced for instant response
    offset: int = 0,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    search: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _: None = Depends(require_module("pms")),
):
    """Get bookings - INSTANT RESPONSE"""
    current_user = await get_current_user(credentials)

    # If search is provided, do a text search across bookings
    if search and search.strip():
        term = search.strip()
        query = {
            "tenant_id": current_user.tenant_id,
            "$or": [
                {"guest_name": {"$regex": term, "$options": "i"}},
                {"room_number": {"$regex": term, "$options": "i"}},
                {"id": {"$regex": term, "$options": "i"}},
            ],
        }
        bookings = []
        async for b in db.bookings.find(query, {"_id": 0}).sort("created_at", -1).limit(limit):
            if not b.get("guest_name") and b.get("guest_id"):
                guest = await db.guests.find_one({"id": b["guest_id"]}, {"name": 1, "_id": 0})
                if guest:
                    b["guest_name"] = guest.get("name", "")
            if b.get("room_id") and not b.get("room_number"):
                room = await db.rooms.find_one({"id": b["room_id"]}, {"room_number": 1, "_id": 0})
                if room:
                    b["room_number"] = room.get("room_number", "")
            bookings.append(b)
        return {"bookings": bookings, "total": len(bookings)}

    # Check pre-warmed cache for default query (no filters)
    if not start_date and not end_date and not status and offset == 0:
        from cache_warmer import cache_warmer
        if cache_warmer:
            cached_data = cache_warmer.get_cached(f"bookings:{current_user.tenant_id}")
            if cached_data:
                # Process and return immediately
                bookings = []
                for booking in cached_data[:limit]:
                    # Enrich guest_name if missing
                    if not booking.get('guest_name') and booking.get('guest_id'):
                        guest = await db.guests.find_one({'id': booking['guest_id']}, {'name': 1, 'first_name': 1, 'last_name': 1, '_id': 0})
                        if guest:
                            booking['guest_name'] = guest.get('name') or f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip() or 'Unknown Guest'
                    # Always enrich room_number from room document (handles room moves)
                    if booking.get('room_id'):
                        room = await db.rooms.find_one({'id': booking['room_id']}, {'room_number': 1, 'room_type': 1, '_id': 0})
                        if room:
                            booking['room_number'] = room.get('room_number', 'Unknown Room')
                            if not booking.get('room_type'):
                                booking['room_type'] = room.get('room_type')
                        elif not booking.get('room_number'):
                            booking['room_number'] = 'Unknown Room'
                    if 'rate_type' in booking:
                        rate_map = {'advance_purchase': 'promotional', 'member': 'promotional'}
                        if booking['rate_type'] in rate_map:
                            booking['rate_type'] = rate_map[booking['rate_type']]
                    if 'market_segment' in booking:
                        segment_map = {'business': 'corporate'}
                        if booking['market_segment'] in segment_map:
                            booking['market_segment'] = segment_map[booking['market_segment']]
                    bookings.append(booking)
                return bookings

    return await reservation_read_service.list_reservations(
        tenant_id=current_user.tenant_id,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
        status=status,
    )


@router.get("/bookings/{booking_id}/override-logs", response_model=list[RateOverrideLog])
@cached(ttl=600, key_prefix="booking_override_logs")  # Cache for 10 min
async def get_booking_override_logs(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get all rate override logs for a specific booking."""
    logs = await db.rate_override_logs.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('timestamp', -1).to_list(100)
    return logs


@router.post("/bookings/{booking_id}/override")

@router.post("/bookings/{booking_id}/approve")
async def approve_booking(
    booking_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Approve a pending booking (hotel-side).

    - Only bookings with status=pending can be approved
    - Idempotent: if already confirmed, returns current state
    - Ownership: booking.tenant_id must match current_user.tenant_id
    """
    _ensure_hotel_context(current_user)

    tenant_id = current_user.tenant_id

    # Lookup booking
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Idempotent: already confirmed
    if booking.get("status") == BookingStatus.CONFIRMED.value:
        return {"status": "ok", "booking": booking}

    if booking.get("status") != BookingStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Booking not in pending state: {booking.get('status')}",
        )

    now = datetime.now(UTC)

    # Atomic-ish: update only if still pending
    res = await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tenant_id, "status": BookingStatus.PENDING.value},
        {"$set": {
            "status": BookingStatus.CONFIRMED.value,
            "approved_at": now,
            "approved_by_user_id": current_user.id,
            "updated_at": now,
        }},
    )

    if res.modified_count != 1:
        # Re-load and check final status
        fresh = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if fresh and fresh.get("status") == BookingStatus.CONFIRMED.value:
            return {"status": "ok", "booking": fresh}
        raise HTTPException(status_code=409, detail="Booking approval in progress")

    # Audit log (best-effort)
    try:
        await create_audit_log(
            tenant_id=tenant_id,
            user=current_user,
            action="BOOKING_APPROVED",
            entity_type="booking",
            entity_id=booking_id,
            changes={"status": BookingStatus.CONFIRMED.value},
            ip_address=request.client.host if request.client else None,
        )
    except Exception as e:
        print(f"audit log failed (approve_booking): {e}")

    final = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    return {"status": "ok", "booking": final, "booking_id": booking_id}



@router.post("/bookings/{booking_id}/reject")
async def reject_booking(
    booking_id: str,
    payload: RejectRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Reject a pending booking with reason.

    - Only bookings with status=pending can be rejected
    - Idempotent: if already rejected, returns current state
    - Ownership: booking.tenant_id must match current_user.tenant_id
    """
    _ensure_hotel_context(current_user)

    tenant_id = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Idempotent: already rejected
    if booking.get("status") == "rejected":
        return {"status": "ok", "booking": booking}

    if booking.get("status") == BookingStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="Booking already cancelled")

    if booking.get("status") != BookingStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Booking not in pending state: {booking.get('status')}",
        )

    now = datetime.now(UTC)

    rejection_fields = {
        "status": REJECTED_STATUS,
        "rejected_at": now,
        "rejected_by_user_id": current_user.id,
        "rejection": {
            "reason_code": payload.reason_code,
            "reason_note": payload.reason_note,
        },
        "updated_at": now,
    }

    res = await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tenant_id, "status": BookingStatus.PENDING.value},
        {"$set": rejection_fields},
    )

    if res.modified_count != 1:
        fresh = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if fresh and fresh.get("status") == REJECTED_STATUS:
            return {"status": "ok", "booking": fresh}
        raise HTTPException(status_code=409, detail="Booking rejection in progress")

    try:
        await create_audit_log(
            tenant_id=tenant_id,
            user=current_user,
            action="BOOKING_REJECTED",
            entity_type="booking",
            entity_id=booking_id,
            changes={
                "status": REJECTED_STATUS,
                "reason_code": payload.reason_code,
                "reason_note": payload.reason_note,
            },
            ip_address=request.client.host if request.client else None,
        )
    except Exception as e:
        print(f"audit log failed (reject_booking): {e}")

    final = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
    return {"status": "ok", "booking": final, "booking_id": booking_id}



@router.put("/pms/bookings/{booking_id}")
async def update_booking(
    booking_id: str,
    booking_data: dict,
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Update an existing booking while preserving the legacy response contract."""
    return await update_reservation_service.update(booking_id, booking_data, current_user, request)


@router.post("/pms/room-move-history")
async def create_room_move_history(
    move_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Log room move history for audit trail.

    Normalises the incoming payload so that every record in
    ``room_move_history`` uses the canonical field names consumed by
    the reservation-detail reader (``from_room_number``,
    ``to_room_number``, ``moved_at``).
    """
    record = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "booking_id": move_data.get("booking_id", ""),
        "from_room_number": move_data.get("old_room"),
        "to_room_number": move_data.get("new_room"),
        "from_room_id": move_data.get("from_room_id"),
        "to_room_id": move_data.get("to_room_id"),
        "reason": move_data.get("reason", ""),
        "moved_by": move_data.get("moved_by", current_user.name),
        "moved_at": move_data.get("timestamp", datetime.now(UTC).isoformat()),
    }

    await db.room_move_history.insert_one({**record})

    return {"message": "Room move logged successfully", "history": record}


@router.post("/pms/bookings/multi-room", response_model=list[Booking])
async def create_multi_room_booking(
    payload: MultiRoomBookingCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a multi-room booking under one group_booking_id.

    - If guest_id is not provided but guest info is, creates the guest first.
    - Creates one Booking per room and links them with group_booking_id.
    - Auto-creates folio for each booking (same behavior as single booking).
    """
    # Resolve guest
    guest_id = payload.guest_id
    if not guest_id and payload.guest:
        guest = Guest(
            tenant_id=current_user.tenant_id,
            **payload.guest.model_dump()
        )
        guest_dict = guest.model_dump()
        guest_dict["created_at"] = guest_dict["created_at"].isoformat()
        await db.guests.insert_one(guest_dict)
        guest_id = guest.id

    if not guest_id:
        raise HTTPException(status_code=400, detail="guest_id or guest details must be provided")

    check_in_dt = datetime.fromisoformat(payload.arrival_date.replace("Z", "+00:00"))
    check_out_dt = datetime.fromisoformat(payload.departure_date.replace("Z", "+00:00"))

    group_id = str(uuid.uuid4())
    created_bookings: list[Booking] = []

    for room_data in payload.rooms:
        room_id = room_data.get("room_id")
        if not room_id:
            raise HTTPException(status_code=400, detail="room_id is required for each room")

        adults = int(room_data.get("adults", 1))
        children = int(room_data.get("children", 0))
        children_ages = room_data.get("children_ages", [])
        total_amount = float(room_data.get("total_amount", 0.0))
        base_rate = room_data.get("base_rate")
        rate_plan = room_data.get("rate_plan")
        package_code = room_data.get("package_code")

        booking = Booking(
            tenant_id=current_user.tenant_id,
            guest_id=guest_id,
            room_id=room_id,
            check_in=check_in_dt,
            check_out=check_out_dt,
            adults=adults,
            children=children,
            children_ages=children_ages,
            guests_count=adults + children,
            total_amount=total_amount,
            base_rate=base_rate,
            channel=payload.channel,
            rate_plan=rate_plan,
            special_requests=payload.special_requests,
            company_id=payload.company_id,
            # Apply corporate / contracted booking attributes from payload
            contracted_rate=payload.contracted_rate,
            rate_type=payload.rate_type,
            market_segment=payload.market_segment,
            cancellation_policy=payload.cancellation_policy,
            group_booking_id=group_id,
        )

        # Attach basic package info as note if provided
        if package_code:
            note = f"Package: {package_code}"
            booking.special_requests = f"{booking.special_requests} | {note}" if booking.special_requests else note

        qr_token = generate_time_based_qr_token(booking.id, expiry_hours=72)
        qr_data = f"booking:{booking.id}:token:{qr_token}"
        qr_code = generate_qr_code(qr_data)
        booking.qr_code = qr_code
        booking.qr_code_data = qr_token

        booking_dict = booking.model_dump()
        booking_dict["check_in"] = booking_dict["check_in"].isoformat()
        booking_dict["check_out"] = booking_dict["check_out"].isoformat()
        booking_dict["created_at"] = booking_dict["created_at"].isoformat()
        from core.atomic_booking import BookingConflictError, create_booking_atomic
        try:
            await create_booking_atomic(booking_dict)
        except BookingConflictError as e:
            raise HTTPException(status_code=409, detail=str(e))

        folio_number = await generate_folio_number(current_user.tenant_id)
        folio = Folio(
            tenant_id=current_user.tenant_id,
            booking_id=booking.id,
            folio_number=folio_number,
            folio_type=FolioType.GUEST,
            guest_id=guest_id,
        )
        folio_dict = folio.model_dump()
        folio_dict["created_at"] = folio_dict["created_at"].isoformat()
        await db.folios.insert_one(folio_dict)

        created_bookings.append(booking)

    return created_bookings
