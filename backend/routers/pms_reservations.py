"""
PMS Reservations Router — Reservation detail, search, and mutation endpoints.
Extracted from pms.py (Stage 3d-reservations).

Routes:
  GET  /reservations/{booking_id}/details-enhanced
  GET  /reservations/double-booking-check
  GET  /reservations/adr-visibility
  POST /reservations/rate-override-panel
  GET  /reservations/{booking_id}/ota-details
  POST /reservations/{booking_id}/extra-charges
  POST /reservations/multi-room
  GET  /reservations/search

Models:
  BookingSourceType, ExtraCharge, MultiRoomBooking,
  ExtraChargeCreate, MultiRoomReservationCreate
"""
import uuid
from datetime import UTC, datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from cache_manager import cached  # v95
from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from core.utils import get_cancellation_policy_details
from models.enums import CancellationPolicyType
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW
from routers.pms_shared import get_guest_name

router = APIRouter(prefix="/api", tags=["pms-reservations"])
security = HTTPBearer()


# ── Models ───────────────────────────────────────────────────────────

class BookingSourceType(str, Enum):
    OTA = "ota"
    WEBSITE = "website"
    CORPORATE = "corporate"
    WALK_IN = "walk_in"
    PHONE = "phone"
    AGENT = "agent"


class ExtraCharge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    booking_id: str
    tenant_id: str
    charge_name: str
    charge_amount: float
    charge_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = None


class MultiRoomBooking(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    group_name: str
    primary_booking_id: str
    related_booking_ids: list[str] = []
    total_rooms: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExtraChargeCreate(BaseModel):
    charge_name: str = Field(..., min_length=1, max_length=200)
    charge_amount: float = Field(..., ge=0, le=1e9)
    notes: str | None = Field(None, max_length=2000)


class MultiRoomReservationCreate(BaseModel):
    group_name: str
    primary_booking_id: str
    related_booking_ids: list[str]


# ── Read paths ───────────────────────────────────────────────────────

@router.get("/reservations/{booking_id}/details-enhanced")
async def get_reservation_details_enhanced(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Enhanced reservation details showing:
    - Cancellation policy
    - OTA commission info
    - Rate breakdown
    """
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Cancellation policy details
    policy = booking.get('cancellation_policy', CancellationPolicyType.H24)
    policy_details = get_cancellation_policy_details(policy)

    # OTA commission
    commission_info = None
    if booking.get('ota_channel'):
        commission_pct = booking.get('commission_pct', 15.0)
        total_amount = booking.get('total_amount', 0)
        commission_amount = total_amount * (commission_pct / 100)
        net_revenue = total_amount - commission_amount

        commission_info = {
            'ota_channel': booking.get('ota_channel'),
            'ota_confirmation': booking.get('ota_confirmation'),
            'commission_pct': commission_pct,
            'commission_amount': round(commission_amount, 2),
            'gross_revenue': round(total_amount, 2),
            'net_revenue': round(net_revenue, 2),
            'payment_model': booking.get('payment_model')
        }

    return {
        'booking_id': booking_id,
        'status': booking.get('status'),
        'cancellation_policy': {
            'type': policy,
            **policy_details
        },
        'commission': commission_info,
        'rate_breakdown': {
            'base_rate': booking.get('base_rate'),
            'total_amount': booking.get('total_amount'),
            'rate_type': booking.get('rate_type'),
            'market_segment': booking.get('market_segment')
        }
    }



@router.get("/reservations/double-booking-check")
@cached(ttl=60, key_prefix="double_booking_check")  # v95 — 60s cache (front-desk operasyonel, kısa TTL)
async def check_double_booking_conflicts(
    date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """
    Double-booking conflict detection engine
    - Identify potential conflicts
    - Room assignment overlaps
    """
    target_date = date or datetime.now().date().isoformat()

    # v95 — Projection: only fields needed for conflict detection (was full-doc fetch)
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$lte': target_date},
        'check_out': {'$gte': target_date}
    }, {'_id': 0, 'id': 1, 'room_id': 1, 'guest_id': 1,
        'check_in': 1, 'check_out': 1, 'status': 1}).to_list(length=None)

    # Group by room
    room_bookings = {}
    for booking in bookings:
        room_id = booking.get('room_id')
        if room_id not in room_bookings:
            room_bookings[room_id] = []
        room_bookings[room_id].append(booking)

    # Batch-fetch all conflicting rooms in one query (avoid N+1)
    conflict_room_ids = [rid for rid, bl in room_bookings.items() if len(bl) > 1 and rid]
    rooms_by_id: dict = {}
    if conflict_room_ids:
        async for r in db.rooms.find(
            {'id': {'$in': conflict_room_ids}, 'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'room_number': 1},
        ):
            rooms_by_id[r['id']] = r

    # Find conflicts
    conflicts = []
    for room_id, room_booking_list in room_bookings.items():
        if len(room_booking_list) > 1:
            room = rooms_by_id.get(room_id)
            conflicts.append({
                'room_id': room_id,
                'room_number': room.get('room_number') if room else 'Unknown',
                'booking_count': len(room_booking_list),
                'bookings': [{
                    'booking_id': b.get('id'),
                    'guest_id': b.get('guest_id'),
                    'check_in': b.get('check_in'),
                    'check_out': b.get('check_out'),
                    'status': b.get('status')
                } for b in room_booking_list]
            })

    return {
        'date': target_date,
        'total_conflicts': len(conflicts),
        'conflicts': conflicts,
        'status': 'conflicts_found' if conflicts else 'no_conflicts'
    }



@router.get("/reservations/adr-visibility")
async def get_adr_and_rate_visibility(
    start_date: str | None = None,
    end_date: str | None = None,
    room_type: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """
    ADR (Average Daily Rate) and rate code visibility
    - Daily ADR
    - By rate code
    - By room type
    """
    # Tur 3: defaults — last 30 days when omitted
    from datetime import date as _d
    from datetime import timedelta as _td
    if not start_date:
        start_date = (_d.today() - _td(days=30)).isoformat()
    if not end_date:
        end_date = _d.today().isoformat()
    # Get all bookings in date range
    bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': start_date,
            '$lte': end_date
        }
    }):
        bookings.append(booking)

    # Calculate ADR
    total_room_revenue = sum(b.get('total_amount', 0) for b in bookings)
    total_room_nights = sum(
        (datetime.fromisoformat(b.get('check_out')) - datetime.fromisoformat(b.get('check_in'))).days
        for b in bookings
    )

    adr = total_room_revenue / total_room_nights if total_room_nights > 0 else 0

    # By rate type
    rate_breakdown = {}
    for booking in bookings:
        rate_type = booking.get('rate_type', 'bar')
        if rate_type not in rate_breakdown:
            rate_breakdown[rate_type] = {
                'bookings': 0,
                'revenue': 0
            }
        rate_breakdown[rate_type]['bookings'] += 1
        rate_breakdown[rate_type]['revenue'] += booking.get('total_amount', 0)

    # Calculate ADR per rate type
    for rate_type, data in rate_breakdown.items():
        data['adr'] = round(data['revenue'] / data['bookings'], 2) if data['bookings'] > 0 else 0

    return {
        'start_date': start_date,
        'end_date': end_date,
        'overall_adr': round(adr, 2),
        'total_room_revenue': round(total_room_revenue, 2),
        'total_room_nights': total_room_nights,
        'total_bookings': len(bookings),
        'rate_breakdown': rate_breakdown
    }


# ── Mutation paths ───────────────────────────────────────────────────

@router.post("/reservations/rate-override-panel")
async def create_rate_override_with_panel(
    booking_id: str,
    new_rate: float = Query(..., ge=0, le=1e9),
    override_reason: str = Query(..., min_length=3, max_length=500),
    current_user: User = Depends(get_current_user)
):
    """
    Rate override panel with authorization tracking.
    Requires `override_rate` permission (admin / super_admin / supervisor).
    Note: `authorized_by` is always set server-side from the calling user;
    it cannot be supplied by the client (audit-trail integrity).
    """
    # Role / permission enforcement (Bug CP fix)
    from modules.pms_core.role_permission_service import RolePermissionService
    RolePermissionService().enforce_permission(current_user.role, "override_rate")

    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    original_rate = booking.get('total_amount', 0)

    # Create override log — authorized_by is always the authenticated user
    override_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'user_id': current_user.id,
        'user_name': current_user.name,
        'original_rate': original_rate,
        'new_rate': new_rate,
        'override_reason': override_reason,
        'authorized_by': current_user.name,
        'timestamp': datetime.now(UTC).isoformat()
    }

    await db.rate_override_logs.insert_one(override_log)

    # Update booking (tenant-pinned defense-in-depth, v107 P0)
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'total_amount': new_rate,
            'base_rate': original_rate,
            'override_reason': override_reason
        }}
    )

    # Create audit log
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="RATE_OVERRIDE",
        entity_type="booking",
        entity_id=booking_id,
        changes={
            'original_rate': original_rate,
            'new_rate': new_rate,
            'reason': override_reason
        }
    )

    return {
        'success': True,
        'booking_id': booking_id,
        'original_rate': original_rate,
        'new_rate': new_rate,
        'override_id': override_log['id'],
        'message': 'Rate override applied successfully'
    }



@router.get("/reservations/{booking_id}/ota-details")
async def get_ota_reservation_details(
    booking_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get detailed OTA reservation information including special requests, multi-room, source, extra charges"""
    current_user = await get_current_user(credentials)

    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get extra charges
    extra_charges = []
    async for charge in db.extra_charges.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }):
        # Remove MongoDB _id field to avoid serialization issues
        if '_id' in charge:
            del charge['_id']
        extra_charges.append(charge)

    # Check if part of multi-room reservation
    multi_room_info = None
    multi_room = await db.multi_room_bookings.find_one({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'primary_booking_id': booking_id},
            {'related_booking_ids': booking_id}
        ]
    })

    if multi_room:
        # Get all related bookings
        related_bookings = []
        all_booking_ids = [multi_room['primary_booking_id']] + multi_room.get('related_booking_ids', [])
        async for related_booking in db.bookings.find({
            'id': {'$in': all_booking_ids},
            'tenant_id': current_user.tenant_id
        }):
            # Get room info
            room = await db.rooms.find_one({'id': related_booking['room_id'], 'tenant_id': current_user.tenant_id})
            related_bookings.append({
                'booking_id': related_booking['id'],
                'room_number': room.get('room_number') if room else 'N/A',
                'guest_name': await get_guest_name(related_booking['guest_id'], current_user.tenant_id)
            })

        multi_room_info = {
            'group_name': multi_room.get('group_name'),
            'total_rooms': multi_room.get('total_rooms'),
            'related_bookings': related_bookings
        }

    # Determine source of booking
    source_of_booking = BookingSourceType.WEBSITE.value  # Default
    if booking.get('ota_channel'):
        source_of_booking = BookingSourceType.OTA.value
    elif booking.get('company_id'):
        source_of_booking = BookingSourceType.CORPORATE.value
    elif booking.get('channel') == 'walk_in':
        source_of_booking = BookingSourceType.WALK_IN.value
    elif booking.get('channel') == 'phone':
        source_of_booking = BookingSourceType.PHONE.value

    return {
        'booking_id': booking_id,
        'special_requests': booking.get('special_requests', ''),
        'adults': booking.get('adults'),
        'children': booking.get('children'),
        'remarks': booking.get('notes', ''),
        'source_of_booking': source_of_booking,
        'ota_channel': booking.get('ota_channel'),
        'ota_confirmation': booking.get('ota_confirmation'),
        'extra_charges': extra_charges,
        'multi_room_info': multi_room_info,
        'commission_pct': booking.get('commission_pct'),
        'payment_model': booking.get('payment_model')
    }


@router.post("/reservations/{booking_id}/extra-charges")
async def add_extra_charge(
    booking_id: str,
    data: ExtraChargeCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("frontdesk")),  # v92 DW
):
    """Add an extra charge to a reservation"""
    current_user = await get_current_user(credentials)

    # Verify booking exists
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Create extra charge
    extra_charge = ExtraCharge(
        booking_id=booking_id,
        tenant_id=current_user.tenant_id,
        charge_name=data.charge_name,
        charge_amount=data.charge_amount,
        notes=data.notes
    )

    await db.extra_charges.insert_one(extra_charge.model_dump())

    return {
        'success': True,
        'message': 'Extra charge added successfully',
        'extra_charge': extra_charge.model_dump()
    }


@router.post("/reservations/multi-room")
async def create_multi_room_reservation(
    data: MultiRoomReservationCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("frontdesk")),  # v92 DW
):
    """Link multiple bookings as a multi-room reservation"""
    current_user = await get_current_user(credentials)

    # Create multi-room booking record
    multi_room = MultiRoomBooking(
        tenant_id=current_user.tenant_id,
        group_name=data.group_name,
        primary_booking_id=data.primary_booking_id,
        related_booking_ids=data.related_booking_ids,
        total_rooms=len(data.related_booking_ids) + 1
    )

    await db.multi_room_bookings.insert_one(multi_room.model_dump())

    return {
        'success': True,
        'message': 'Multi-room reservation created',
        'multi_room_id': multi_room.id
    }



@router.get("/reservations/search")
async def search_reservations(
    query: str = None,
    check_in: str = None,
    check_out: str = None,
    status: str = None,
    booking_id: str = None,
    phone: str = None,
    email: str = None,
    current_user: User = Depends(get_current_user)
):
    """
    Comprehensive reservation search with multiple filters
    Search by: guest name, booking ID, phone, email, date range, status
    """
    try:
        filter_dict = {'tenant_id': current_user.tenant_id}

        # Search conditions
        search_conditions = []

        import re as _re

        if query:
            # Index-serviceable anchored prefix match on the bookings
            # `<field>_lower` companion fields (backed by
            # (tenant_id, <field>_lower) indexes) — replaces the un-indexable
            # unanchored case-insensitive regex scan that drove Atlas
            # query-targeting alerts. (#247 pattern; the internal `id` substring
            # branch is dropped because it has no companion index.)
            from security.search_normalize import prefix_conditions
            _conds = prefix_conditions(['guest_name', 'booking_number'], query)
            if _conds:
                search_conditions.append({'$or': _conds})

        if booking_id:
            search_conditions.append({'id': booking_id})

        if phone:
            # Find guest by phone first — MUST be tenant-scoped to prevent IDOR.
            # Dual-read: exact _hash_phone (encrypted) OR legacy plaintext regex.
            from security.encrypted_lookup import guest_pii_regex_or_conditions
            guest = await db.guests.find_one({
                'tenant_id': current_user.tenant_id,
                '$or': guest_pii_regex_or_conditions('phone', phone),
            })
            if guest:
                search_conditions.append({'guest_id': guest['id']})

        if email:
            # Find guest by email first — MUST be tenant-scoped to prevent IDOR.
            # Dual-read: exact _hash_email (encrypted) OR legacy plaintext regex.
            from security.encrypted_lookup import guest_pii_regex_or_conditions
            guest = await db.guests.find_one({
                'tenant_id': current_user.tenant_id,
                '$or': guest_pii_regex_or_conditions('email', email),
            })
            if guest:
                search_conditions.append({'guest_id': guest['id']})

        if check_in:
            search_conditions.append({'check_in': {'$gte': check_in}})

        if check_out:
            search_conditions.append({'check_out': {'$lte': check_out}})

        if status:
            search_conditions.append({'status': status})

        # Combine all conditions
        if search_conditions:
            filter_dict['$and'] = search_conditions

        # Find bookings
        bookings = await db.bookings.find(filter_dict, {'_id': 0}).sort('check_in', -1).limit(50).to_list(50)

        # v95 — Batch enrich with guest/room data via single $in lookup (was N+1, ~14s).
        # Tenant-scoped on both ends to prevent IDOR.
        guest_ids = {b['guest_id'] for b in bookings if b.get('guest_id')}
        room_ids = {b['room_id'] for b in bookings if b.get('room_id')}

        guests_map: dict[str, dict] = {}
        if guest_ids:
            from security.encrypted_lookup import decrypt_guest_doc
            async for g in db.guests.find(
                {'tenant_id': current_user.tenant_id, 'id': {'$in': list(guest_ids)}},
                {'_id': 0, 'id': 1, 'phone': 1, 'email': 1},
            ):
                guests_map[g['id']] = decrypt_guest_doc(g)

        rooms_map: dict[str, dict] = {}
        if room_ids:
            async for r in db.rooms.find(
                {'tenant_id': current_user.tenant_id, 'id': {'$in': list(room_ids)}},
                {'_id': 0, 'id': 1, 'room_number': 1, 'room_type': 1},
            ):
                rooms_map[r['id']] = r

        for booking in bookings:
            guest = guests_map.get(booking.get('guest_id'))
            if guest:
                booking['guest_phone'] = guest.get('phone')
                booking['guest_email'] = guest.get('email')
            room = rooms_map.get(booking.get('room_id'))
            if room:
                booking['room_number'] = room.get('room_number')
                booking['room_type'] = room.get('room_type')

        return {
            'bookings': bookings,
            'count': len(bookings),
            'search_query': query,
            'filters_applied': {
                'check_in': check_in,
                'check_out': check_out,
                'status': status,
                'phone': phone,
                'email': email
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
