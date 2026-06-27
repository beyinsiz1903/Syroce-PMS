"""
guest_app

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.enums import UserRole
from models.schemas import (
    User,
)
from modules.pms_core.role_permission_service import require_role

from .room_service_realtime import emit_order_event, order_stream


# ── Booking ownership helper ──────────────────────────────────────────────────
async def _assert_guest_owns_booking(booking: dict, current_user: User) -> None:
    """Enforce booking ownership for guest_app principals.

    Staff roles may access any booking within their tenant without restriction.
    Callers with the ``guest_app`` role must own the booking — the tenant-scoped
    guest record associated with their e-mail address must match
    ``booking.guest_id``.  Raises HTTP 403 otherwise.

    This mirrors the authorization logic already applied by
    ``_user_can_subscribe_to_booking()`` (WebSocket path) and
    ``_assert_booking_accessible()`` (checkin_router), ensuring a single
    consistent ownership contract across all booking-scoped guest endpoints.
    """
    role = getattr(current_user.role, "value", str(current_user.role))
    if role != "guest_app":
        return  # Staff / admin callers are not restricted to their own bookings.

    # Collect *all* tenant-scoped guest records for this e-mail address (mirrors
    # the multi-record lookup in _user_can_subscribe_to_booking) so that a guest
    # with duplicate records is not incorrectly denied access.
    guest_ids: list[str] = []
    from security.encrypted_lookup import build_guest_pii_query
    async for g in db.guests.find(
        {"tenant_id": current_user.tenant_id, **build_guest_pii_query("email", current_user.email)},
        {"_id": 0, "id": 1},
    ):
        gid = g.get("id")
        if gid:
            guest_ids.append(gid)

    if not guest_ids or booking.get("guest_id") not in guest_ids:
        raise HTTPException(status_code=403, detail="Bu rezervasyon size ait değil")


# Staff-only allow-list for PATCH /room-service-orders/{id}/status.
# Module-level so tests can pin it.
_ROOM_SERVICE_STAFF_ROLES = (
    UserRole.SUPER_ADMIN,
    UserRole.ADMIN,
    UserRole.SUPERVISOR,
    UserRole.FRONT_DESK,
    UserRole.HOUSEKEEPING,
    UserRole.STAFF,
)

DEFAULT_UPSELL_PRICES = {
    "early_checkin": 25.00,
    "late_checkout": 35.00,
    "airport_transfer": 50.00,
}


async def _get_upsell_prices(tenant_id: str) -> dict:
    """Return per-tenant upsell prices, falling back to defaults for any missing key."""
    prices = dict(DEFAULT_UPSELL_PRICES)
    doc = await db.upsell_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if doc and isinstance(doc.get("prices"), dict):
        for k, v in doc["prices"].items():
            if k in prices:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv >= 0:
                    prices[k] = fv
    return prices


# ============= PHASE H: GUEST CRM + UPSELL AI + MESSAGING =============









_MANUAL_UPSELL_TYPES = {
    "early_checkin", "late_checkout", "airport_transfer",
    "room_upgrade", "spa_package", "dining_credit", "champagne", "custom",
}














async def check_rate_limit(tenant_id: str, channel: str, limit_per_hour: int = 100) -> bool:
    """Check if rate limit is exceeded for messaging"""
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    count = await db.messages.count_documents({
        'tenant_id': tenant_id,
        'channel': channel,
        'sent_at': {'$gte': one_hour_ago}
    })

    return count < limit_per_hour








# Router will be included at the very end after ALL endpoints are defined

logger = logging.getLogger(__name__)



# ========================================

# 1. EXTERNAL REVIEW API INTEGRATION (Booking.com, Google, TripAdvisor)





# 2. IN-HOUSE SURVEY SYSTEM





# 3. DEPARTMENT-BASED SATISFACTION TRACKING




# ============= GUEST MOBILE APP ENDPOINTS =============

# rbac-allow: cache-rbac — GUEST portal — kendi rezervasyonları


































router = APIRouter(prefix="/api", tags=["guest-experience"])


# ── GET /guest/bookings ──
@router.get("/guest/bookings")
async def get_guest_bookings(
    current_user: User = Depends(get_current_user)
):
    """Get guest's bookings across ALL hotels (multi-tenant support)"""
    # Find ALL guest records across all tenants with this email
    # Dual-read: encrypted _hash_email OR legacy plaintext; tenant-scoped (IDOR).
    from security.encrypted_lookup import build_guest_pii_query
    guest_records = []
    async for guest in db.guests.find(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)}
    ):
        guest_records.append(guest)

    guest_ids = [g['id'] for g in guest_records]

    if not guest_ids:
        # No guest records found, return empty
        return {'active_bookings': [], 'past_bookings': []}

    # Get ALL bookings across all tenants for these guest IDs — N+1 fix: bulk fetch
    all_bookings = []
    bookings_list = await db.bookings.find({'guest_id': {'$in': guest_ids}}).sort('check_in', -1).to_list(5000)
    b_room_ids = list({b.get('room_id') for b in bookings_list if b.get('room_id')})
    b_guest_ids = list({b.get('guest_id') for b in bookings_list if b.get('guest_id')})
    b_tenant_ids = list({b.get('tenant_id') for b in bookings_list if b.get('tenant_id')})
    rooms_map: dict = {}
    guests_map: dict = {}
    tenants_map: dict = {}
    if b_room_ids:
        async for r in db.rooms.find({'id': {'$in': b_room_ids}}):
            rooms_map[r['id']] = r
    if b_guest_ids:
        async for g in db.guests.find({'id': {'$in': b_guest_ids}}):
            guests_map[g['id']] = g
    if b_tenant_ids:
        async for t in db.tenants.find({'id': {'$in': b_tenant_ids}}):
            tenants_map[t['id']] = t

    for booking in bookings_list:
        room = rooms_map.get(booking.get('room_id'))
        guest = guests_map.get(booking.get('guest_id'))
        tenant = tenants_map.get(booking.get('tenant_id'))

        # Helper to make datetime timezone-aware
        def make_aware(dt_str):
            if not dt_str:
                return None
            try:
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except Exception:
                return None

        check_in_dt = make_aware(booking.get('check_in'))
        now_utc = datetime.now(UTC)

        booking_data = {
            'id': booking.get('id'),
            'tenant_id': booking.get('tenant_id'),
            'confirmation_number': booking.get('confirmation_number', booking.get('id')[:8].upper()),
            'check_in': booking.get('check_in'),
            'check_out': booking.get('check_out'),
            'status': booking.get('status'),
            'guests_count': booking.get('adults', 1) + booking.get('children', 0),
            'total_amount': booking.get('total_amount', 0),
            'guest_name': guest.get('name') if guest else current_user.name,
            'qr_code_data': booking.get('qr_code_data'),
            'can_checkin': booking.get('status') == 'confirmed' and check_in_dt and check_in_dt <= now_utc,
            'can_communicate': booking.get('status') in ['confirmed', 'checked_in'],
            'can_order_services': booking.get('status') == 'checked_in',
            # Nested hotel data for frontend
            'hotel': {
                'id': tenant.get('id') if tenant else None,
                'property_name': tenant.get('property_name', 'Hotel') if tenant else 'Hotel',
                'hotel_name': tenant.get('hotel_name', tenant.get('property_name', 'Hotel')) if tenant else 'Hotel',
                'address': tenant.get('address', 'City Center') if tenant else 'City Center'
            },
            # Nested room data for frontend
            'room': {
                'room_number': room.get('room_number', 'TBA') if room else 'TBA',
                'room_type': room.get('room_type', 'Standard') if room else 'Standard',
                'floor': room.get('floor', 1) if room else 1
            }
        }

        all_bookings.append(booking_data)

    # Separate active and past
    now = datetime.now(UTC)
    active_bookings = []
    past_bookings = []

    for b in all_bookings:
        try:
            # Parse checkout date and make it timezone aware if needed
            checkout_dt = datetime.fromisoformat(b['check_out'])
            if checkout_dt.tzinfo is None:
                checkout_dt = checkout_dt.replace(tzinfo=UTC)

            # Categorize booking
            if b['status'] in ['confirmed', 'checked_in', 'guaranteed'] and checkout_dt >= now:
                active_bookings.append(b)
            elif b['status'] == 'checked_out' or (checkout_dt < now and b['status'] not in ['checked_in', 'confirmed', 'guaranteed']):
                past_bookings.append(b)
        except Exception:
            # If date parsing fails, default to past booking
            if b['status'] == 'checked_out':
                past_bookings.append(b)
            else:
                active_bookings.append(b)

    return {
        'active_bookings': active_bookings,
        'past_bookings': past_bookings[:10]  # Last 10
    }
# ── GET /guest/loyalty ──
@router.get("/guest/loyalty")
async def get_guest_loyalty(
    current_user: User = Depends(get_current_user)
):
    """Get guest loyalty information across ALL hotels (multi-tenant support)"""
    # Find ALL guest records across all tenants with this email
    # Dual-read: encrypted _hash_email OR legacy plaintext; tenant-scoped (IDOR).
    from security.encrypted_lookup import build_guest_pii_query
    guest_records = []
    async for guest in db.guests.find(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)}
    ):
        guest_records.append(guest)

    if not guest_records:
        return {
            'total_points': 0,
            'loyalty_programs': [],
            'upcoming_rewards': [],
            'global_tier': 'bronze'
        }

    # Build loyalty programs array - one per hotel — N+1 fix: bulk fetch
    loyalty_programs = []
    total_points_all_hotels = 0

    g_tenant_ids = list({g.get('tenant_id') for g in guest_records if g.get('tenant_id')})
    l_tenants_map: dict = {}
    benefits_map: dict = {}
    if g_tenant_ids:
        async for t in db.tenants.find({'id': {'$in': g_tenant_ids}}):
            l_tenants_map[t['id']] = t
        async for b in db.loyalty_benefits.find({'tenant_id': {'$in': g_tenant_ids}}):
            benefits_map[(b.get('tenant_id'), b.get('tier'))] = b

    for guest in guest_records:
        tenant = l_tenants_map.get(guest.get('tenant_id'))
        loyalty_points = guest.get('loyalty_points', 0)
        loyalty_tier = guest.get('loyalty_tier', 'bronze')
        total_points_all_hotels += loyalty_points

        benefits = benefits_map.get((guest.get('tenant_id'), loyalty_tier))

        # Calculate points to next tier

        next_tier = None
        points_to_next = 0

        if loyalty_tier == 'bronze':
            next_tier = 'silver'
            points_to_next = 1000 - loyalty_points
        elif loyalty_tier == 'silver':
            next_tier = 'gold'
            points_to_next = 5000 - loyalty_points
        elif loyalty_tier == 'gold':
            next_tier = 'platinum'
            points_to_next = 10000 - loyalty_points

        # Get recent point transactions for this hotel
        transactions = []
        async for txn in db.loyalty_transactions.find({
            'tenant_id': guest.get('tenant_id'),
            'guest_id': guest.get('id')
        }).sort('created_at', -1).limit(5):
            transactions.append(txn)

        loyalty_programs.append({
            'id': guest.get('id'),
            'hotel_id': guest.get('tenant_id'),
            'hotel_name': tenant.get('property_name', 'Hotel') if tenant else 'Hotel',
            'tier': loyalty_tier,
            'points': loyalty_points,
            'next_tier': next_tier,
            'points_to_next_tier': max(0, points_to_next) if next_tier else 0,
            'tier_benefits': benefits.get('benefits', []) if benefits else [],
            'recent_transactions': transactions
        })

    # Calculate global tier based on total points across all hotels
    if total_points_all_hotels >= 10000:
        global_tier = 'platinum'
    elif total_points_all_hotels >= 5000:
        global_tier = 'gold'
    elif total_points_all_hotels >= 1000:
        global_tier = 'silver'
    else:
        global_tier = 'bronze'

    return {
        'total_points': total_points_all_hotels,
        'global_tier': global_tier,
        'loyalty_programs': loyalty_programs,
        'upcoming_rewards': [
            {
                'name': 'Free Night Stay',
                'points_required': 5000,
                'points_remaining': max(0, 5000 - total_points_all_hotels)
            },
            {
                'name': 'Room Upgrade',
                'points_required': 2000,
                'points_remaining': max(0, 2000 - total_points_all_hotels)
            },
            {
                'name': 'Late Checkout',
                'points_required': 500,
                'points_remaining': max(0, 500 - total_points_all_hotels)
            }
        ]
    }
# ── GET /guest/notification-preferences ──
@router.get("/guest/notification-preferences")
async def get_notification_preferences(
    current_user: User = Depends(get_current_user)
):
    """Get guest notification preferences (user-level, not tenant-specific)"""
    prefs = await db.guest_notification_preferences.find_one(
        {'user_id': current_user.id},
        {'_id': 0}  # Exclude MongoDB ObjectId
    )

    if not prefs:
        # Default preferences
        return {
            'user_id': current_user.id,
            'email_notifications': True,
            'sms_notifications': False,
            'push_notifications': True,
            'whatsapp_notifications': False,
            'booking_confirmations': True,
            'check_in_reminders': True,
            'promotional_offers': True,
            'loyalty_updates': True
        }

    return prefs
# ── PUT /guest/notification-preferences ──
@router.put("/guest/notification-preferences")
async def update_notification_preferences(
    preferences: dict,
    current_user: User = Depends(get_current_user)
):
    """Update guest notification preferences (user-level, applies to all hotels)"""
    # Add user_id to the update
    update_data = {**preferences, 'user_id': current_user.id}

    await db.guest_notification_preferences.update_one(
        {'user_id': current_user.id},
        {'$set': update_data},
        upsert=True
    )

    return {'message': 'Preferences updated successfully', 'preferences': update_data}
# ── POST /guest/device-token ──
@router.post("/guest/device-token")
async def register_device_token(
    device_token: str,
    platform: str,  # ios, android, web
    current_user: User = Depends(get_current_user)
):
    """Register device token for push notifications"""
    await db.guest_device_tokens.update_one(
        {
            'tenant_id': current_user.tenant_id,
            'user_id': current_user.id,
            'device_token': device_token
        },
        {
            '$set': {
                'tenant_id': current_user.tenant_id,
                'user_id': current_user.id,
                'device_token': device_token,
                'platform': platform,
                'updated_at': datetime.now(UTC).isoformat()
            }
        },
        upsert=True
    )

    return {
        'success': True,
        'message': 'Device token registered'
    }
# ── GET /guest/room-service-menu ──
@router.get("/guest/room-service-menu")
async def get_room_service_menu(
    current_user: User = Depends(get_current_user)
):
    """Get room service menu"""
    menu_items = []
    async for item in db.room_service_menu.find({
        'tenant_id': current_user.tenant_id,
        'available': True
    }).sort('category', 1):
        menu_items.append(item)

    # If no menu exists, return sample menu
    if not menu_items:
        return {
            'categories': [
                {
                    'name': 'Breakfast',
                    'items': [
                        {'id': '1', 'name': 'Continental Breakfast', 'price': 15.00, 'description': 'Croissant, juice, coffee'},
                        {'id': '2', 'name': 'American Breakfast', 'price': 18.00, 'description': 'Eggs, bacon, toast, coffee'}
                    ]
                },
                {
                    'name': 'Lunch & Dinner',
                    'items': [
                        {'id': '3', 'name': 'Club Sandwich', 'price': 14.00, 'description': 'Triple decker with fries'},
                        {'id': '4', 'name': 'Caesar Salad', 'price': 12.00, 'description': 'With grilled chicken'}
                    ]
                },
                {
                    'name': 'Beverages',
                    'items': [
                        {'id': '5', 'name': 'Fresh Juice', 'price': 6.00, 'description': 'Orange or apple'},
                        {'id': '6', 'name': 'Soft Drinks', 'price': 4.00, 'description': 'Coca Cola, Sprite, Fanta'}
                    ]
                }
            ]
        }

    # Group by category
    categories = {}
    for item in menu_items:
        cat = item.get('category', 'Other')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    return {
        'categories': [
            {'name': cat, 'items': items}
            for cat, items in categories.items()
        ]
    }
# ── POST /guest/room-service-order ──
class _RoomServiceOrderBody(BaseModel):
    booking_id: str
    items: list[dict]
    special_instructions: str | None = None


@router.post("/guest/room-service-order")
async def create_room_service_order(
    body: _RoomServiceOrderBody,
    current_user: User = Depends(get_current_user)
):
    """Create room service order"""
    booking_id = body.booking_id
    items = body.items
    special_instructions = body.special_instructions
    # Verify booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found")

    await _assert_guest_owns_booking(booking, current_user)

    # Calculate total
    total_amount = sum(item.get('price', 0) * item.get('quantity', 1) for item in items)

    order = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'room_id': booking.get('room_id'),
        'guest_id': current_user.id,
        'items': items,
        'total_amount': total_amount,
        'special_instructions': special_instructions,
        'status': 'pending',  # pending, confirmed, preparing, delivered, cancelled
        'ordered_at': datetime.now(UTC).isoformat(),
        'estimated_delivery': (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    }

    await db.room_service_orders.insert_one(order)

    # Task #64: push the new order to every guest WS subscribed to this
    # booking so the order list lights up immediately on the placing
    # device *and* on a second device the same guest may have logged in
    # on. Best-effort — a broken broadcast must not roll back the order.
    # Task #69: also enrich with room_number so the staff dashboard can
    # render the new row immediately, without a follow-up REST refetch.
    await _enrich_order_with_room_number(order)
    await emit_order_event(order, event_type="created")

    # Post charge to folio
    folio = await db.folios.find_one({
        'booking_id': booking_id,
        'folio_type': 'guest',
        'status': 'open'
    })

    if folio:
        charge = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'folio_id': folio['id'],
            'booking_id': booking_id,
            'date': datetime.now(UTC).date().isoformat(),
            'charge_category': 'food',
            'description': 'Room Service',
            'unit_price': total_amount,
            'quantity': 1,
            'amount': total_amount,
            'tax_rate': 0.18,
            'tax_amount': round(total_amount * 0.18, 2),
            'total': round(total_amount * 1.18, 2),
            'posted_by': 'Guest App'
        }

        await db.folio_charges.insert_one(charge)

    return {
        'success': True,
        'order_id': order['id'],
        'estimated_delivery': order['estimated_delivery'],
        'total_amount': total_amount
    }
# ── GET /guest/room-service-orders/{booking_id} ──
@router.get("/guest/room-service-orders/{booking_id}")
async def get_room_service_orders(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get room service orders for a booking"""
    booking = await db.bookings.find_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0, 'id': 1, 'guest_id': 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    await _assert_guest_owns_booking(booking, current_user)

    orders = []
    async for order in db.room_service_orders.find({
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id
    }).sort('ordered_at', -1):
        orders.append(order)

    return {'orders': orders}
# ── PATCH /guest/room-service-orders/{order_id}/status ──
_VALID_ORDER_STATUSES = {
    "pending", "confirmed", "preparing", "delivered", "cancelled",
}


class _UpdateOrderStatusBody(BaseModel):
    status: str


@router.patch("/guest/room-service-orders/{order_id}/status")
async def update_room_service_order_status(
    order_id: str,
    body: _UpdateOrderStatusBody,
    current_user: User = Depends(get_current_user),
    _role: None = Depends(require_role(*_ROOM_SERVICE_STAFF_ROLES)),
):
    """Staff-only: update order status and broadcast `status_changed`
    over the per-booking WS channel. Tenant-scoped."""
    if body.status not in _VALID_ORDER_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status; expected one of {sorted(_VALID_ORDER_STATUSES)}",
        )
    order = await db.room_service_orders.find_one({
        'id': order_id,
        'tenant_id': current_user.tenant_id,
    })
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    update = {
        'status': body.status,
        'updated_at': datetime.now(UTC).isoformat(),
        'updated_by': current_user.id,
    }
    await db.room_service_orders.update_one(
        {'id': order_id, 'tenant_id': current_user.tenant_id},
        {'$set': update},
    )
    order.update(update)

    # Best-effort fan-out to subscribed guest WS clients. Failures are
    # logged inside emit_order_event and never bubble up to the staff
    # caller — the DB write is the source of truth, polling will catch
    # up if the channel is down.
    await _enrich_order_with_room_number(order)
    await emit_order_event(order, event_type="status_changed")

    return {
        'success': True,
        'order_id': order_id,
        'status': body.status,
    }


async def _enrich_order_with_room_number(order: dict) -> None:
    """Mutate ``order`` to add a ``room_number`` field by looking up
    the room from ``order.room_id`` (with a fallback through
    ``bookings.room_id`` for older order docs that didn't store it).
    Best-effort — a missing room is not an error and leaves the field
    as ``None``. Used so WS broadcasts include the human-friendly room
    number without staff dashboards needing a follow-up REST fetch."""
    if order.get('room_number'):
        return
    tenant_id = order.get('tenant_id')
    if not tenant_id:
        return
    room_id = order.get('room_id')
    booking_id = order.get('booking_id')
    try:
        if not room_id and booking_id:
            booking = await db.bookings.find_one(
                {'id': booking_id, 'tenant_id': tenant_id},
                {'_id': 0, 'room_id': 1, 'room_number': 1},
            )
            if booking:
                room_id = booking.get('room_id') or room_id
                if booking.get('room_number'):
                    order['room_number'] = booking['room_number']
        if room_id and not order.get('room_number'):
            room = await db.rooms.find_one(
                {'id': room_id, 'tenant_id': tenant_id},
                {'_id': 0, 'room_number': 1, 'number': 1},
            )
            if room:
                order['room_number'] = room.get('room_number') or room.get('number')
    except Exception as e:
        logging.getLogger(__name__).warning(
            "room_number enrichment failed tenant=%s order=%s: %s",
            tenant_id, order.get('id'), e,
        )


# ── GET /guest/staff/room-service-orders ──
# Task #69: tenant-wide staff list of today's open room-service orders so
# kitchen / front-desk dashboards can drive the PATCH status endpoint
# without first asking the guest which booking they're on.
_STAFF_OPEN_STATUSES = {"pending", "confirmed", "preparing"}


@router.get("/guest/staff/room-service-orders")
async def list_staff_room_service_orders(
    include_completed: bool = False,
    current_user: User = Depends(get_current_user),
    _role: None = Depends(require_role(*_ROOM_SERVICE_STAFF_ROLES)),
):
    """Staff dashboard list. Returns today's room-service orders for
    the caller's tenant, enriched with `room_number`. By default only
    open statuses (pending/confirmed/preparing) are returned;
    `include_completed=true` also returns delivered/cancelled."""
    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    query: dict = {
        'tenant_id': current_user.tenant_id,
        'ordered_at': {'$gte': today_start},
    }
    if not include_completed:
        query['status'] = {'$in': sorted(_STAFF_OPEN_STATUSES)}

    raw_orders = await db.room_service_orders.find(
        query, {'_id': 0}
    ).sort('ordered_at', 1).to_list(500)

    # 1) Booking fallback first: for any order missing a `room_id`,
    #    look up the booking's `room_id` / `room_number`. Older docs
    #    may not have stored `room_id` on the order.
    booking_ids = sorted({
        o.get('booking_id') for o in raw_orders
        if o.get('booking_id') and not o.get('room_id')
    })
    booking_room_map: dict = {}
    if booking_ids:
        async for b in db.bookings.find(
            {'id': {'$in': list(booking_ids)},
             'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'room_id': 1, 'room_number': 1},
        ):
            booking_room_map[b['id']] = {
                'room_id': b.get('room_id'),
                'room_number': b.get('room_number'),
            }

    # 2) Single bulk rooms lookup that spans both the direct
    #    `order.room_id` and the booking-fallback `room_id` (N+1 fix).
    room_ids: set[str] = set()
    for o in raw_orders:
        if o.get('room_id'):
            room_ids.add(o['room_id'])
        elif o.get('booking_id') in booking_room_map:
            br_room = booking_room_map[o['booking_id']].get('room_id')
            if br_room:
                room_ids.add(br_room)

    rooms_map: dict = {}
    if room_ids:
        async for r in db.rooms.find(
            {'id': {'$in': sorted(room_ids)},
             'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'room_number': 1, 'number': 1},
        ):
            rooms_map[r['id']] = r.get('room_number') or r.get('number')

    orders_out = []
    for o in raw_orders:
        room_number = rooms_map.get(o.get('room_id'))
        if not room_number and o.get('booking_id') in booking_room_map:
            br = booking_room_map[o['booking_id']]
            room_number = (
                rooms_map.get(br.get('room_id')) or br.get('room_number')
            )
        orders_out.append({
            **o,
            'room_number': room_number,
        })

    return {'orders': orders_out}


async def _authenticate_ws_token(token: str | None) -> dict | None:
    """Mirror of ``get_current_user`` for a JWT passed as a WS query
    param (RN's WebSocket can't set Authorization headers). Returns
    ``{'user_id', 'tenant_id', 'role'}`` or ``None``."""
    if not token:
        return None
    if isinstance(token, str) and token.lower().startswith("bearer "):
        token = token[7:]

    try:
        from jose import jwt

        from core.security import (
            JWT_ALGORITHM,
            JWT_SECRET,
            _user_doc_cache_get,
            _user_doc_cache_set,
            is_jti_revoked,
        )
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception as e:
        logging.getLogger(__name__).debug(
            "room-service WS auth decode failed: %s", e
        )
        return None

    user_id = payload.get("user_id")
    jwt_tenant = payload.get("tenant_id")
    if not user_id or not jwt_tenant:
        return None

    # jti revocation parity with HTTP path.
    jti = payload.get("jti")
    try:
        if jti and await is_jti_revoked(jti):
            return None
    except Exception as e:
        logging.getLogger(__name__).warning(
            "room-service WS jti check failed: %s", e
        )
        return None

    # User-doc lookup (cached) — guards deleted users + tenant mismatch.
    try:
        user_doc = _user_doc_cache_get(user_id)
        if user_doc is None:
            user_doc = await db.users.find_one(
                {'$or': [{'id': user_id}, {'user_id': user_id}]},
                {'_id': 0, 'id': 1, 'user_id': 1, 'role': 1, 'tenant_id': 1,
                 'email': 1, 'tokens_invalid_before': 1},
            )
            if user_doc:
                _user_doc_cache_set(user_id, user_doc)
    except Exception as e:
        logging.getLogger(__name__).warning(
            "room-service WS user lookup failed: %s", e
        )
        return None

    if not user_doc:
        return None

    doc_tenant = user_doc.get('tenant_id')
    if doc_tenant and jwt_tenant != doc_tenant:
        logging.getLogger(__name__).warning(
            "room-service WS tenant mismatch: user=%s jwt=%s doc=%s",
            user_id, jwt_tenant, doc_tenant,
        )
        return None

    # Mass-revocation watermark (token iat must be >= tokens_invalid_before).
    invalid_before = user_doc.get('tokens_invalid_before')
    if invalid_before:
        iat = payload.get('iat')
        if not iat or int(iat) < int(invalid_before):
            return None

    return {
        'user_id': user_id,
        'tenant_id': jwt_tenant,
        'role': user_doc.get('role'),
        'email': user_doc.get('email'),
    }


async def _user_can_subscribe_to_booking(identity: dict, booking_id: str) -> bool:
    """Booking-level authz for the room-service WS.

    Staff roles in `_ROOM_SERVICE_STAFF_ROLES` may subscribe to any
    booking in their tenant (kitchen display, front desk monitoring).
    Guest principals must own the booking — i.e. one of their
    email-keyed `db.guests` records is referenced by `booking.guest_id`.
    """
    role = identity.get('role')
    tenant_id = identity['tenant_id']
    role_value = getattr(role, 'value', role)

    if role_value in {r.value for r in _ROOM_SERVICE_STAFF_ROLES} or role_value == 'super_admin':
        return True

    booking = await db.bookings.find_one(
        {'id': booking_id, 'tenant_id': tenant_id},
        {'_id': 0, 'id': 1, 'guest_id': 1},
    )
    if not booking:
        return False

    email = identity.get('email')
    if not email:
        return False

    # Tenant-scope the guest lookup so an attacker can't piggy-back a
    # same-email guest record from another tenant onto this booking.
    guest_ids = []
    from security.encrypted_lookup import build_guest_pii_query
    async for g in db.guests.find(
        {'tenant_id': tenant_id, **build_guest_pii_query('email', email)}, {'_id': 0, 'id': 1}
    ):
        gid = g.get('id')
        if gid:
            guest_ids.append(gid)

    return booking.get('guest_id') in guest_ids


# ── WS /guest/ws/room-service-orders/{booking_id} ──
@router.websocket("/guest/ws/room-service-orders/{booking_id}")
async def ws_room_service_orders(websocket: WebSocket, booking_id: str):
    """Per-booking room-service order stream. JWT in `?token=` query
    param. Auth parity with HTTP via `_authenticate_ws_token`. Closes
    4401 on auth failure, 4403 if the caller is not the booking guest
    or staff in the booking's tenant."""
    identity = await _authenticate_ws_token(websocket.query_params.get("token"))
    if not identity:
        await websocket.close(code=4401, reason="unauthorized")
        return
    tenant_id = identity['tenant_id']

    if not await _user_can_subscribe_to_booking(identity, booking_id):
        await websocket.close(code=4403, reason="forbidden")
        return

    await order_stream.connect(websocket, tenant_id, booking_id)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                try:
                    await websocket.send_text('{"type":"pong"}')
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.getLogger(__name__).warning(
            "room-service WS loop error tenant=%s booking=%s: %s",
            tenant_id, booking_id, e,
        )
    finally:
        await order_stream.disconnect(websocket, tenant_id, booking_id)


# ── WS /guest/staff/ws/room-service-orders ──
# Task #69: tenant-wide staff stream so a kitchen / front-desk dashboard
# stays in sync with every PATCH status across every active booking
# without opening one socket per booking. Auth parity with the
# per-booking WS via the same JWT-in-query path; staff role required.
@router.websocket("/guest/staff/ws/room-service-orders")
async def ws_staff_room_service_orders(websocket: WebSocket):
    identity = await _authenticate_ws_token(websocket.query_params.get("token"))
    if not identity:
        await websocket.close(code=4401, reason="unauthorized")
        return

    role_value = getattr(identity.get('role'), 'value', identity.get('role'))
    allowed = {r.value for r in _ROOM_SERVICE_STAFF_ROLES}
    if role_value not in allowed and role_value != 'super_admin':
        await websocket.close(code=4403, reason="forbidden")
        return

    tenant_id = identity['tenant_id']
    await order_stream.connect_staff(websocket, tenant_id)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                try:
                    await websocket.send_text('{"type":"pong"}')
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.getLogger(__name__).warning(
            "room-service staff WS loop error tenant=%s: %s",
            tenant_id, e,
        )
    finally:
        await order_stream.disconnect_staff(websocket, tenant_id)


# ── POST /guest/request ──
@router.post("/guest/request")
async def create_guest_request(
    booking_id: str,
    request_type: str,  # housekeeping, maintenance, concierge, other
    description: str,
    priority: str = 'normal',  # low, normal, high, urgent
    current_user: User = Depends(get_current_user)
):
    """Create guest request"""
    # Verify booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found")

    await _assert_guest_owns_booking(booking, current_user)

    request = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'room_id': booking.get('room_id'),
        'guest_id': current_user.id,
        'request_type': request_type,
        'description': description,
        'priority': priority,
        'status': 'pending',  # pending, in_progress, completed, cancelled
        'created_at': datetime.now(UTC).isoformat(),
        'resolved_at': None
    }

    await db.guest_requests.insert_one(request)

    # Create task for appropriate department
    department_map = {
        'housekeeping': 'housekeeping',
        'maintenance': 'engineering',
        'concierge': 'concierge',
        'other': 'front_desk'
    }

    task = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'title': f'Guest Request: {request_type}',
        'description': description,
        'department': department_map.get(request_type, 'front_desk'),
        'priority': priority,
        'status': 'pending',
        'room_id': booking.get('room_id'),
        'related_request_id': request['id'],
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.staff_tasks.insert_one(task)

    return {
        'success': True,
        'request_id': request['id'],
        'message': 'Request submitted successfully'
    }
# ── GET /guest/requests/{booking_id} ──
@router.get("/guest/requests/{booking_id}")
async def get_guest_requests(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get guest requests for a booking"""
    booking = await db.bookings.find_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0, 'id': 1, 'guest_id': 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    await _assert_guest_owns_booking(booking, current_user)

    requests = []
    async for req in db.guest_requests.find({
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id
    }).sort('created_at', -1):
        requests.append(req)

    return {'requests': requests}
# ── GET /guest/profile ──
@router.get("/guest/profile")
async def get_guest_profile(
    current_user: User = Depends(get_current_user)
):
    """Get guest profile"""
    # Dual-read by email (encrypted _hash_email OR plaintext) + decrypt PII for display.
    from security.encrypted_lookup import build_guest_pii_query, decrypt_guest_doc
    guest = decrypt_guest_doc(await db.guests.find_one(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)}
    ))

    if not guest:
        return {
            'name': current_user.name,
            'email': current_user.email,
            'phone': '',
            'nationality': '',
            'preferences': {}
        }

    return {
        'id': guest.get('id'),
        'name': guest.get('name'),
        'email': guest.get('email'),
        'phone': guest.get('phone', ''),
        'nationality': guest.get('nationality', ''),
        'date_of_birth': guest.get('date_of_birth', ''),
        'preferences': guest.get('preferences', {}),
        'loyalty_tier': guest.get('loyalty_tier', 'bronze'),
        'loyalty_points': guest.get('loyalty_points', 0)
    }
# ── PUT /guest/profile ──
@router.put("/guest/profile")
async def update_guest_profile(
    profile_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update guest profile"""
    # Dual-read by email + decrypt so the existing PII used as update defaults
    # (and passed to encrypt_guest_update) is plaintext, not ciphertext.
    from security.encrypted_lookup import build_guest_pii_query, decrypt_guest_doc
    guest = decrypt_guest_doc(await db.guests.find_one(
        {'tenant_id': current_user.tenant_id, **build_guest_pii_query('email', current_user.email)}
    ))

    if not guest:
        # Create guest profile
        guest_id = str(uuid.uuid4())
        guest_data = {
            'id': guest_id,
            'tenant_id': current_user.tenant_id,
            'name': profile_data.get('name', current_user.name),
            'email': current_user.email,
            'phone': profile_data.get('phone', ''),
            'nationality': profile_data.get('nationality', ''),
            'date_of_birth': profile_data.get('date_of_birth', ''),
            'preferences': profile_data.get('preferences', {}),
            'created_at': datetime.now(UTC).isoformat()
        }
        from security.guest_write import encrypt_guest_insert
        guest_data = encrypt_guest_insert(guest_data)
        await db.guests.insert_one(guest_data)
        return {'success': True, 'message': 'Profile created'}

    # Update existing profile
    update_data = {
        'name': profile_data.get('name', guest.get('name')),
        'phone': profile_data.get('phone', guest.get('phone')),
        'nationality': profile_data.get('nationality', guest.get('nationality')),
        'date_of_birth': profile_data.get('date_of_birth', guest.get('date_of_birth')),
        'preferences': profile_data.get('preferences', guest.get('preferences', {})),
        'updated_at': datetime.now(UTC).isoformat()
    }
    # encrypt_guest_update recomputes the plaintext name companions (normalized
    # + merged _ng_name from the stored `guest`) AND encrypts PII fields
    # (phone/date_of_birth) with their _hash_ tokens before persistence.
    from security.guest_write import encrypt_guest_update
    update_data = encrypt_guest_update(update_data, guest)

    await db.guests.update_one(
        {'id': guest['id']},
        {'$set': update_data}
    )

    return {'success': True, 'message': 'Profile updated'}
# ── POST /guest/web-checkin/{booking_id} ──
@router.post("/guest/web-checkin/{booking_id}")
async def web_checkin(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Perform web check-in"""
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'confirmed'
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or already checked in")

    await _assert_guest_owns_booking(booking, current_user)

    # Check if check-in date is today or past
    check_in_date = datetime.fromisoformat(booking['check_in'])
    if check_in_date.date() > datetime.now(UTC).date():
        raise HTTPException(status_code=400, detail="Cannot check in before check-in date")

    # Update booking status to web_checked_in
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'status': 'web_checked_in',
            'web_checkin_at': datetime.now(UTC).isoformat()
        }}
    )

    # Generate digital key QR code
    digital_key = {
        'booking_id': booking_id,
        'room_id': booking.get('room_id'),
        'valid_from': datetime.now(UTC).isoformat(),
        'valid_until': booking['check_out'],
        'key_code': str(uuid.uuid4())[:8].upper()
    }

    room_ready = False
    room_status: str | None = None
    room_id = booking.get('room_id')
    if room_id:
        room_doc = await db.rooms.find_one(
            {'id': room_id, 'tenant_id': current_user.tenant_id},
            {'status': 1, 'housekeeping_status': 1}
        )
        if room_doc:
            room_status = (
                room_doc.get('status')
                or room_doc.get('housekeeping_status')
                or ''
            ).lower()
            room_ready = room_status in {
                'clean', 'inspected', 'ready', 'vacant_clean', 'available'
            }

    return {
        'success': True,
        'message': 'Web check-in completed',
        'digital_key': digital_key,
        'qr_code_data': booking.get('qr_code_data'),
        'room_ready': room_ready,
        'room_status': room_status,
        'instructions': (
            'Show this QR code at the front desk or use it with smart lock'
            if room_ready else
            'Odanız hazırlanıyor, lobide bekleyebilir veya odanız hazır olduğunda bildirim alabilirsiniz.'
        ),
    }
