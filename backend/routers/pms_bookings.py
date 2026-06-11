"""
PMS Bookings Router — Extracted from routers/pms.py (Stage 2 decomposition)
Booking CRUD, approval/rejection, multi-room bookings, room move history.
"""
import logging

from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW
from modules.pms_core.role_permission_service import require_module as require_module_v101  # v101 DW

logger = logging.getLogger(__name__)
import hashlib
import json as _json
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from core.database import db
from core.helpers import create_audit_log, require_module
from core.pagination import PaginationParams, paginate
from core.security import get_current_user
from core.utils import generate_folio_number, generate_qr_code, generate_time_based_qr_token
from modules.pms_core.role_permission_service import require_op  # v82 DR

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
    guest_name: str = Field(..., min_length=1, max_length=200)
    room_id: str
    check_in: str
    check_out: str
    total_amount: float = Field(..., ge=0, le=1e12)
    guest_id: str | None = None
    adults: int = Field(1, ge=0, le=50)
    children: int = Field(0, ge=0, le=50)
    daily_rate: float | None = Field(None, ge=0, le=1e12)


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

    try:
        ci_dt = datetime.fromisoformat(data.check_in.replace('Z', '+00:00'))
        co_dt = datetime.fromisoformat(data.check_out.replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError) as _e:
        raise HTTPException(status_code=400, detail=f"Gecersiz tarih formati: {_e}")
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
        # Deterministic guest_id from idempotency key so retries with the same
        # Idempotency-Key produce the same guest_id (otherwise the downstream
        # request_hash differs and idempotency check fails).
        idem_key = request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key") or ""
        if idem_key:
            guest_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{tenant_id}:walkin:{idem_key}"))
        else:
            guest_id = str(uuid.uuid4())
        existing_walkin = await db.guests.find_one({"id": guest_id, "tenant_id": tenant_id}, {"_id": 0})
        if not existing_walkin:
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
            from security.guest_write import encrypt_guest_insert
            guest_doc = encrypt_guest_insert(guest_doc)
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


@router.get("/pms/arrivals")
async def get_arrivals(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Arrivals by check-in date.

    Filters bookings whose `check_in` falls between `start_date` and `end_date`
    (inclusive, ISO date strings). Defaults to today if no range is given.
    Status is restricted to confirmed / guaranteed / checked_in.
    """
    from datetime import date, timedelta

    today_str = datetime.now(UTC).date().isoformat()
    start = start_date or today_str
    end = end_date or start

    # `check_in` may be stored as date-only ("YYYY-MM-DD") or datetime
    # ("YYYY-MM-DDTHH:MM:SS"). Use a date-only lower bound and an
    # exclusive next-day upper bound so both formats are matched
    # correctly via lexicographic comparison.
    try:
        end_date_obj = date.fromisoformat(end)
    except ValueError:
        end_date_obj = date.fromisoformat(today_str)
    upper_exclusive = (end_date_obj + timedelta(days=1)).isoformat()

    query = {
        "tenant_id": current_user.tenant_id,
        "check_in": {"$gte": start, "$lt": upper_exclusive},
        "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
    }

    safe_limit = max(1, min(int(limit or 200), 500))
    bookings = await db.bookings.find(query, {"_id": 0}).sort("check_in", 1).limit(safe_limit).to_list(length=safe_limit)

    # Enrich guest_name / room_number — guests koleksiyonu otorite.
    # bookings.guest_name eski sync artigi olabilir ("V4 Refund" gibi); guests'te
    # gercek isim varsa override et. (get_bookings ile ayni mantik.)
    all_guest_ids = {b["guest_id"] for b in bookings if b.get("guest_id")}
    missing_room_ids = {b["room_id"] for b in bookings if b.get("room_id") and not b.get("room_number")}

    if all_guest_ids:
        guest_name_map: dict[str, str] = {}
        async for g in db.guests.find(
            {"id": {"$in": list(all_guest_ids)}, "tenant_id": current_user.tenant_id},
            {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1},
        ):
            nm = g.get("name") or f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()
            if nm:
                guest_name_map[g["id"]] = nm
        for b in bookings:
            if b.get("guest_id") and b["guest_id"] in guest_name_map:
                b["guest_name"] = guest_name_map[b["guest_id"]]

    if missing_room_ids:
        room_num_map: dict[str, str] = {}
        async for r in db.rooms.find(
            {"id": {"$in": list(missing_room_ids)}, "tenant_id": current_user.tenant_id},
            {"_id": 0, "id": 1, "room_number": 1},
        ):
            room_num_map[r["id"]] = r.get("room_number", "")
        for b in bookings:
            if b.get("room_id") and not b.get("room_number"):
                b["room_number"] = room_num_map.get(b["room_id"], "")

    # Enrich each booking with `online_checkin_id_photo_uploaded`: tells the
    # reception UI whether a guest-uploaded ID photo exists so the
    # "Kimlik fotoğrafını görüntüle" button is only shown when there is
    # actually a photo to view. Single batched query (no N+1).
    booking_ids = [b["id"] for b in bookings if b.get("id")]
    if booking_ids:
        photo_flags: dict[str, bool] = {}
        async for ci in db.online_checkins.find(
            {
                "booking_id": {"$in": booking_ids},
                "tenant_id": current_user.tenant_id,
            },
            {"_id": 0, "booking_id": 1, "id_photo_uploaded": 1, "id_photo": 1},
        ):
            has_photo = bool(
                ci.get("id_photo_uploaded")
                and isinstance(ci.get("id_photo"), dict)
                and ci["id_photo"].get("photo_id")
            )
            photo_flags[ci["booking_id"]] = (
                photo_flags.get(ci["booking_id"], False) or has_photo
            )
        for b in bookings:
            b["online_checkin_id_photo_uploaded"] = bool(
                photo_flags.get(b.get("id"), False)
            )

    return {"bookings": bookings, "total": len(bookings), "start_date": start, "end_date": end}


@router.get("/pms/bookings")
async def get_bookings(
    p: PaginationParams = Depends(paginate(default_limit=30, max_limit=500)),
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    search: str | None = None,
    # Use FastAPI's dependency injection so `get_current_user` is shared
    # with the `require_module` dependency (FastAPI caches dependency
    # results within a single request). The previous code path took the
    # raw bearer credentials and then called `await get_current_user(...)`
    # manually, which DOES NOT participate in the dependency cache —
    # auth was therefore paying for two full JWT-decode + decrypt cycles
    # per request. Routing through Depends collapses that to one.
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Get bookings - INSTANT RESPONSE"""
    limit, offset = p.limit, p.offset

    # If search is provided, do a text search across bookings
    if search and search.strip():
        # Index-serviceable anchored prefix match on the bookings
        # `<field>_lower` companion fields (backed by (tenant_id, <field>_lower)
        # indexes) — replaces the un-indexable unanchored case-insensitive regex
        # scan that drove Atlas query-targeting alerts. (#247 pattern; the
        # `room_number`/`id` substring branches are dropped because they have no
        # companion index, and `booking_number` prefix search is added.)
        from security.search_normalize import prefix_conditions
        conds = prefix_conditions(['guest_name', 'booking_number'], search)
        query = {"tenant_id": current_user.tenant_id}
        if conds:
            query["$or"] = conds
        bookings = await db.bookings.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
        # Batch-fetch ALL guest names — guests koleksiyonu otorite. bookings.guest_name
        # eski sync/import artigi olabilir ("V4 Refund", "X" gibi); guests'te gercek
        # isim varsa onu tercih et, yoksa booking.guest_name fallback.
        all_guest_ids = {b["guest_id"] for b in bookings if b.get("guest_id")}
        missing_room_ids = {b["room_id"] for b in bookings if b.get("room_id") and not b.get("room_number")}
        from core.guest_name_utils import display_guest_name, is_placeholder_guest_name
        guest_name_map: dict[str, str] = {}
        if all_guest_ids:
            async for g in db.guests.find(
                {"id": {"$in": list(all_guest_ids)}, "tenant_id": current_user.tenant_id},
                {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1},
            ):
                nm = g.get("name") or f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()
                # Walk-in placeholder ("C4", "V4 Refund", "X") reddet — fallback devreye girsin.
                if nm and not is_placeholder_guest_name(nm):
                    guest_name_map[g["id"]] = nm
        room_num_map: dict[str, str] = {}
        if missing_room_ids:
            async for r in db.rooms.find(
                {"id": {"$in": list(missing_room_ids)}, "tenant_id": current_user.tenant_id},
                {"_id": 0, "id": 1, "room_number": 1},
            ):
                room_num_map[r["id"]] = r.get("room_number", "")
        for b in bookings:
            if b.get("guest_id") and b["guest_id"] in guest_name_map:
                b["guest_name"] = guest_name_map[b["guest_id"]]
            elif is_placeholder_guest_name(b.get("guest_name")):
                b["guest_name"] = display_guest_name(b.get("guest_name"), b.get("guest_id"))
            if b.get("room_id") and not b.get("room_number"):
                b["room_number"] = room_num_map.get(b["room_id"], "")
        return {"bookings": bookings, "total": len(bookings)}

    # Check pre-warmed cache for default query (no filters)
    if not start_date and not end_date and not status and offset == 0:
        from cache_warmer import cache_warmer
        if cache_warmer:
            cached_data = cache_warmer.get_cached(f"bookings:{current_user.tenant_id}")
            if cached_data:
                page = [dict(b) for b in cached_data[:limit]]
                # Batch-fetch guests and rooms once. Prefer the pre-warmed
                # tenant-scoped maps from cache_warmer (RAM, ~0ms). Fall back
                # to a tenant-filtered Atlas query only when the maps were
                # not warmed yet OR a booking references an id that wasn't
                # in the warm snapshot (newly-created guest, etc.). This is
                # what cuts the bookings endpoint from ~1.8s to ~200ms.
                # guests koleksiyonu otorite — bookings.guest_name eski sync artigi
                # ("V4 Refund" gibi) olabilir. TUM guest_id'ler icin lookup yap,
                # gercek isim varsa booking.guest_name'i override et.
                all_guest_ids = {b['guest_id'] for b in page if b.get('guest_id')}
                room_ids = {b['room_id'] for b in page if b.get('room_id')}

                warm_guest_map = cache_warmer.get_cached(f"guest_map:{current_user.tenant_id}") or {}
                warm_room_map = cache_warmer.get_cached(f"room_map:{current_user.tenant_id}") or {}

                from core.guest_name_utils import display_guest_name, is_placeholder_guest_name
                guest_map: dict[str, str] = {gid: warm_guest_map[gid] for gid in all_guest_ids if gid in warm_guest_map}
                room_map: dict[str, dict] = {rid: warm_room_map[rid] for rid in room_ids if rid in warm_room_map}

                # Atlas fallback ONLY for ids the warm snapshot didn't cover.
                still_missing_guests = all_guest_ids - guest_map.keys()
                if still_missing_guests:
                    # Always scope batch lookups by tenant_id — the cache key is
                    # tenant-scoped but the lookup must be too, both for
                    # multi-tenant isolation AND to hit the
                    # (tenant_id, id) compound index instead of scanning by id.
                    async for g in db.guests.find(
                        {'id': {'$in': list(still_missing_guests)}, 'tenant_id': current_user.tenant_id},
                        {'_id': 0, 'id': 1, 'name': 1, 'first_name': 1, 'last_name': 1},
                    ):
                        nm = g.get('name') or f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()
                        # Walk-in placeholder reddet — display fallback devreye girsin.
                        if nm and not is_placeholder_guest_name(nm):
                            guest_map[g['id']] = nm
                still_missing_rooms = room_ids - room_map.keys()
                if still_missing_rooms:
                    async for r in db.rooms.find(
                        {'id': {'$in': list(still_missing_rooms)}, 'tenant_id': current_user.tenant_id},
                        {'_id': 0, 'id': 1, 'room_number': 1, 'room_type': 1},
                    ):
                        room_map[r['id']] = r
                rate_map = {'advance_purchase': 'promotional', 'member': 'promotional'}
                segment_map = {'business': 'corporate'}
                bookings = []
                for booking in page:
                    if booking.get('guest_id') and booking['guest_id'] in guest_map:
                        booking['guest_name'] = guest_map[booking['guest_id']]
                    elif is_placeholder_guest_name(booking.get('guest_name')):
                        # Placeholder ("C4", "V4 Refund", "X") veya bos → fallback
                        booking['guest_name'] = display_guest_name(
                            booking.get('guest_name'), booking.get('guest_id')
                        )
                    if booking.get('room_id'):
                        room = room_map.get(booking['room_id'])
                        if room:
                            booking['room_number'] = room.get('room_number', 'Unknown Room')
                            if not booking.get('room_type'):
                                booking['room_type'] = room.get('room_type')
                        elif not booking.get('room_number'):
                            booking['room_number'] = 'Unknown Room'
                    if booking.get('rate_type') in rate_map:
                        booking['rate_type'] = rate_map[booking['rate_type']]
                    if booking.get('market_segment') in segment_map:
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
async def get_booking_override_logs(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v82 DR: rate override audit = finance/manager
):
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
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
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
        logger.info(f"audit log failed (approve_booking): {e}")

    final = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})

    # ── Messaging Automation: booking confirmed ──
    try:
        from modules.messaging.automation import fire_booking_event
        if final:
            await fire_booking_event(tenant_id, "booking_confirmed", final)
    except Exception:
        pass

    return {"status": "ok", "booking": final, "booking_id": booking_id}



@router.post("/bookings/{booking_id}/reject")
async def reject_booking(
    booking_id: str,
    payload: RejectRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
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
        logger.info(f"audit log failed (reject_booking): {e}")

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
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
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


@router.post("/pms/bookings/multi-room")
async def create_multi_room_booking(
    payload: MultiRoomBookingCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Create a multi-room booking under one group_booking_id.

    - If guest_id is not provided but guest info is, creates the guest first.
    - Creates one Booking per room and links them with group_booking_id.
    - Auto-creates folio for each booking (same behavior as single booking).

    Bug Z fix: Idempotency-Key header verildiyse, aynı key + aynı payload retry'ı
    cached response döner; aynı key + farklı payload → 409. Hiç key yoksa
    her istek random group oluşturur (geri uyumlu).
    """
    # ── Bug Z: Idempotency enforcement ──────────────────────────────────
    idem_key = (request.headers.get("Idempotency-Key") or
                request.headers.get("idempotency-key") or "").strip()
    payload_hash = None
    if idem_key:
        try:
            raw = _json.dumps(payload.model_dump(), sort_keys=True, default=str)
            payload_hash = hashlib.sha256(raw.encode()).hexdigest()
        except Exception:
            payload_hash = None
        deterministic_group = str(uuid.uuid5(
            uuid.NAMESPACE_OID,
            f"{current_user.tenant_id}:multiroom:{idem_key}"
        ))
        existing = await db.bookings.find(
            {"group_booking_id": deterministic_group, "tenant_id": current_user.tenant_id},
            {"_id": 0},
        ).to_list(length=100)
        if existing:
            existing_hash = existing[0].get("idempotency_payload_hash")
            if payload_hash and existing_hash and existing_hash != payload_hash:
                raise HTTPException(status_code=409,
                                    detail="Idempotency-Key reused with different payload")
            return existing
    else:
        deterministic_group = None
    # ────────────────────────────────────────────────────────────────────

    # Resolve guest
    guest_id = payload.guest_id
    if not guest_id and payload.guest:
        guest = Guest(
            tenant_id=current_user.tenant_id,
            **payload.guest.model_dump()
        )
        guest_dict = guest.model_dump()
        guest_dict["created_at"] = guest_dict["created_at"].isoformat()
        from security.guest_write import encrypt_guest_insert
        guest_dict = encrypt_guest_insert(guest_dict)
        await db.guests.insert_one(guest_dict)
        guest_id = guest.id

    if not guest_id:
        raise HTTPException(status_code=400, detail="guest_id or guest details must be provided")

    try:
        check_in_dt = datetime.fromisoformat(payload.arrival_date.replace("Z", "+00:00"))
        check_out_dt = datetime.fromisoformat(payload.departure_date.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as _e:
        raise HTTPException(status_code=400, detail=f"Gecersiz tarih formati: {_e}")
    if check_out_dt <= check_in_dt:
        raise HTTPException(status_code=400, detail="Cikis tarihi giristen sonra olmalidir")

    if not isinstance(payload.rooms, list) or not payload.rooms:
        raise HTTPException(status_code=400, detail="En az bir oda gerekli")
    if len(payload.rooms) > 50:
        raise HTTPException(status_code=400, detail="Cok fazla oda (max 50)")

    # PRE-VALIDATE: tum oda ID'leri once dogrula — partial booking olmasin
    requested_room_ids = []
    for room_data in payload.rooms:
        if not isinstance(room_data, dict):
            raise HTTPException(status_code=400, detail="Her oda bir obje olmalidir")
        rid = room_data.get("room_id")
        if not rid or not isinstance(rid, str):
            raise HTTPException(status_code=400, detail="Her oda icin gecerli room_id gerekli")
        requested_room_ids.append(rid)
    found_rooms = await db.rooms.find(
        {"id": {"$in": requested_room_ids}, "tenant_id": current_user.tenant_id},
        {"id": 1, "_id": 0},
    ).to_list(length=len(requested_room_ids))
    found_set = {r["id"] for r in found_rooms}
    missing = [r for r in requested_room_ids if r not in found_set]
    if missing:
        raise HTTPException(status_code=404, detail=f"Oda(lar) bulunamadi: {missing[:5]}")

    group_id = deterministic_group or str(uuid.uuid4())
    created_bookings: list[Booking] = []

    async def _rollback_group(reason: str):
        """Saga compensation: delete all bookings+folios in this group and release locks.
        Bug Y fix: rollback failures artık sessiz yutulmuyor, logger ile rapor ediliyor."""
        from core.atomic_booking import release_booking_nights
        compensation_errors = []
        for b in created_bookings:
            bid = b.get("id")
            if not bid:
                continue
            try:
                await db.bookings.delete_one({"id": bid, "tenant_id": current_user.tenant_id})
                await db.folios.delete_many({"booking_id": bid, "tenant_id": current_user.tenant_id})
                await release_booking_nights(current_user.tenant_id, bid, reason=reason)
            except Exception as ce:
                compensation_errors.append(f"booking={bid}: {ce}")
        if compensation_errors:
            logger.error("SAGA COMPENSATION PARTIAL FAILURE group=%s reason=%s errors=%s",
                         group_id, reason, compensation_errors)

    for room_data in payload.rooms:
      try:
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

          # Booking modeli yalin (extra=ignore) oldugundan dict'i elle insa ediyoruz
          special_req = payload.special_requests
          if package_code:
              note = f"Package: {package_code}"
              special_req = f"{special_req} | {note}" if special_req else note

          booking_id = str(uuid.uuid4())
          qr_token = generate_time_based_qr_token(booking_id, expiry_hours=72)
          qr_data = f"booking:{booking_id}:token:{qr_token}"
          qr_code = generate_qr_code(qr_data)

          booking_dict = {
              "id": booking_id,
              "tenant_id": current_user.tenant_id,
              "guest_id": guest_id,
              "room_id": room_id,
              "check_in": check_in_dt.isoformat(),
              "check_out": check_out_dt.isoformat(),
              "adults": adults,
              "children": children,
              "children_ages": children_ages,
              "guests_count": adults + children,
              "total_amount": total_amount,
              "base_rate": base_rate,
              "channel": getattr(payload.channel, "value", payload.channel) if payload.channel else "direct",
              "rate_plan": rate_plan or "Standard",
              "special_requests": special_req,
              "company_id": payload.company_id,
              "contracted_rate": getattr(payload.contracted_rate, "value", payload.contracted_rate) if payload.contracted_rate else None,
              "rate_type": getattr(payload.rate_type, "value", payload.rate_type) if payload.rate_type else None,
              "market_segment": getattr(payload.market_segment, "value", payload.market_segment) if payload.market_segment else None,
              "cancellation_policy": getattr(payload.cancellation_policy, "value", payload.cancellation_policy) if payload.cancellation_policy else None,
              "group_booking_id": group_id,
              "status": "pending",
              "qr_code": qr_code,
              "qr_code_data": qr_token,
              "created_at": datetime.utcnow().isoformat(),
              "paid_amount": 0.0,
          }
          if payload_hash:
              booking_dict["idempotency_payload_hash"] = payload_hash
          from core.atomic_booking import BookingConflictError, create_booking_atomic
          try:
              await create_booking_atomic(booking_dict)
          except BookingConflictError as e:
              await _rollback_group(reason="group_conflict_rollback")
              # F8N — structured detail (mirrors create_reservation_service).
              raise HTTPException(status_code=409, detail={
                  "message": str(e),
                  "conflicting_booking_id": getattr(e, "conflicting_booking_id", None),
                  "conflict_type": getattr(e, "conflict_type", "booking"),
                  "conflict_window": {
                      "room_id": room_id,
                      "check_in": check_in_dt.isoformat(),
                      "check_out": check_out_dt.isoformat(),
                  },
              })
          except Exception as e:
              await _rollback_group(reason="group_unknown_rollback")
              logger.exception("Multi-room booking atomic insert failed group=%s booking=%s: %s", group_id, booking_id, e)
              raise HTTPException(status_code=500, detail="Booking creation failed; group rolled back")

          # Folio insert — Saga: fail olursa az önceki booking + tüm grup geri al
          try:
              folio_number = await generate_folio_number(current_user.tenant_id)
              folio = Folio(
                  tenant_id=current_user.tenant_id,
                  booking_id=booking_id,
                  folio_number=folio_number,
                  folio_type=FolioType.GUEST,
                  guest_id=guest_id,
              )
              folio_dict = folio.model_dump()
              folio_dict["created_at"] = folio_dict["created_at"].isoformat()
              await db.folios.insert_one(folio_dict)
          except Exception as e:
              # Az önceki booking henüz created_bookings'e eklenmedi — onu da temizle
              try:
                  from core.atomic_booking import release_booking_nights
                  await db.bookings.delete_one({"id": booking_id, "tenant_id": current_user.tenant_id})
                  await release_booking_nights(current_user.tenant_id, booking_id, reason="folio_insert_failed")
              except Exception:
                  pass
              await _rollback_group(reason="folio_insert_failed")
              logger.exception("Multi-room folio insert failed group=%s booking=%s: %s", group_id, booking_id, e)
              raise HTTPException(status_code=500, detail="Folio creation failed; group rolled back")

          created_bookings.append(booking_dict)

      except HTTPException:
          # rollback grup, sonra orijinal HTTPException'i yeniden firlat
          await _rollback_group(reason="iter_http_error")
          raise
      except Exception as e:
          await _rollback_group(reason="iter_unexpected_error")
          logger.exception("Multi-room loop unexpected error: %s", e)
          raise HTTPException(status_code=500, detail="Multi-room booking failed; group rolled back")

    return created_bookings
