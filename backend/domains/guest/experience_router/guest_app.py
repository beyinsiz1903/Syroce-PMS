"""
guest_app

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
import math
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from core.cache import cached
from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from models.schemas import (
    CreateDepartmentFeedbackRequest,
    CreateSurveyRequest,
    ExternalReviewWebhookRequest,
    RMSSuggestion,
    SubmitSurveyResponseRequest,
    User,
)
from modules.pms_core.role_permission_service import require_op  # v98 DW
from shared_kernel.idempotency import (
    claim_idempotency,
    complete_idempotency,
    get_idempotency_key,
    release_idempotency,
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


































# ============================================================================
# REVIEW INVITES — Misafire e-posta ile değerlendirme linki gönder
# ============================================================================

def _render_review_invite_email(*, hotel_name: str, guest_name: str, link: str) -> tuple[str, str]:
    """Build (html, text) bodies for the review invite e-mail."""
    safe_guest = (guest_name or "Değerli Misafirimiz").strip() or "Değerli Misafirimiz"
    text = (
        f"Merhaba {safe_guest},\n\n"
        f"{hotel_name} olarak konaklamanızı değerlendirmenizi rica ederiz.\n"
        f"Aşağıdaki bağlantıdan birkaç dakikanızı ayırabilirsiniz:\n\n"
        f"{link}\n\n"
        f"Geri bildiriminiz hizmet kalitemizi geliştirmemize yardımcı oluyor.\n"
        f"Teşekkür ederiz.\n\n"
        f"{hotel_name}"
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f6f7fb;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
        <tr><td style="padding:28px 32px 8px 32px;">
          <h1 style="margin:0;font-size:20px;color:#111827;">{hotel_name}</h1>
          <p style="margin:4px 0 0 0;color:#6b7280;font-size:13px;">Konaklama Değerlendirmesi</p>
        </td></tr>
        <tr><td style="padding:16px 32px 8px 32px;">
          <p style="font-size:15px;line-height:1.6;margin:0 0 12px 0;">Merhaba <strong>{safe_guest}</strong>,</p>
          <p style="font-size:15px;line-height:1.6;margin:0 0 16px 0;">
            Bizi tercih ettiğiniz için teşekkür ederiz. Konaklamanızla ilgili görüşlerinizi
            bizimle paylaşmanız hizmet kalitemizi geliştirmemize yardımcı olacaktır.
          </p>
          <p style="font-size:15px;line-height:1.6;margin:0 0 24px 0;">
            Birkaç dakikanızı ayırarak değerlendirme yapabilir misiniz?
          </p>
        </td></tr>
        <tr><td align="center" style="padding:8px 32px 24px 32px;">
          <a href="{link}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:15px;">Değerlendirme Yap</a>
        </td></tr>
        <tr><td style="padding:0 32px 24px 32px;">
          <p style="font-size:12px;color:#6b7280;margin:0 0 4px 0;">Bağlantı çalışmıyorsa kopyalayıp tarayıcınıza yapıştırabilirsiniz:</p>
          <p style="font-size:12px;color:#374151;word-break:break-all;margin:0;"><a href="{link}" style="color:#2563eb;">{link}</a></p>
        </td></tr>
        <tr><td style="padding:16px 32px 24px 32px;border-top:1px solid #e5e7eb;">
          <p style="font-size:12px;color:#9ca3af;margin:0;">{hotel_name} • Bu e-posta konaklamanız sebebiyle gönderilmiştir.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
    return html, text




_REVIEW_INVITE_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")
_REVIEW_INVITE_INDEX_READY = False


async def _ensure_review_invite_indexes() -> None:
    """Idempotently ensure unique index on review_invites.token."""
    global _REVIEW_INVITE_INDEX_READY
    if _REVIEW_INVITE_INDEX_READY:
        return
    try:
        await db.review_invites.create_index("token", unique=True, name="uniq_token")
        await db.review_invites.create_index("tenant_id", name="by_tenant")
    except Exception as exc:  # pragma: no cover - best effort
        logging.warning("[review-invite] index ensure failed: %s", exc)
    _REVIEW_INVITE_INDEX_READY = True


def _validate_review_invite_token(token: str) -> None:
    if not token or not _REVIEW_INVITE_TOKEN_RE.match(token):
        raise HTTPException(status_code=400, detail="Geçersiz bağlantı")


def _check_invite_expiry_or_raise(expires_raw) -> None:
    """Fail-closed: missing or unparseable expiry is treated as expired."""
    if not expires_raw:
        raise HTTPException(status_code=410, detail="Bu davetin süresi dolmuş")
    try:
        exp = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=410, detail="Bu davetin süresi dolmuş") from exc
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Bu davetin süresi dolmuş")

router = APIRouter(prefix="/api", tags=["guest-experience"])


# ── GET /guest/bookings ──
@router.get("/guest/bookings")
@cached(ttl=300, key_prefix="guest_bookings_history")  # Cache for 5 min
async def get_guest_bookings(
    current_user: User = Depends(get_current_user)
):
    """Get guest's bookings across ALL hotels (multi-tenant support)"""
    # Find ALL guest records across all tenants with this email
    guest_records = []
    async for guest in db.guests.find({'email': current_user.email}):
        guest_records.append(guest)

    guest_ids = [g['id'] for g in guest_records]

    if not guest_ids:
        # No guest records found, return empty
        return {'active_bookings': [], 'past_bookings': []}

    # Get ALL bookings across all tenants for these guest IDs
    all_bookings = []
    async for booking in db.bookings.find({'guest_id': {'$in': guest_ids}}).sort('check_in', -1):
        # Get room details
        room = await db.rooms.find_one({'id': booking.get('room_id')})

        # Get guest details
        guest = await db.guests.find_one({'id': booking.get('guest_id')})

        # Get tenant/hotel details for THIS booking
        tenant = await db.tenants.find_one({'id': booking.get('tenant_id')})

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
    guest_records = []
    async for guest in db.guests.find({'email': current_user.email}):
        guest_records.append(guest)

    if not guest_records:
        return {
            'total_points': 0,
            'loyalty_programs': [],
            'upcoming_rewards': [],
            'global_tier': 'bronze'
        }

    # Build loyalty programs array - one per hotel
    loyalty_programs = []
    total_points_all_hotels = 0

    for guest in guest_records:
        tenant = await db.tenants.find_one({'id': guest.get('tenant_id')})
        loyalty_points = guest.get('loyalty_points', 0)
        loyalty_tier = guest.get('loyalty_tier', 'bronze')
        total_points_all_hotels += loyalty_points

        # Get loyalty program benefits for this hotel
        benefits = await db.loyalty_benefits.find_one({
            'tenant_id': guest.get('tenant_id'),
            'tier': loyalty_tier
        })

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
@router.post("/guest/room-service-order")
async def create_room_service_order(
    booking_id: str,
    items: list[dict],
    special_instructions: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Create room service order"""
    # Verify booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found")

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
    orders = []
    async for order in db.room_service_orders.find({
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id
    }).sort('ordered_at', -1):
        orders.append(order)

    return {'orders': orders}
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
    guest = await db.guests.find_one({
        'email': current_user.email,
        'tenant_id': current_user.tenant_id
    })

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
    guest = await db.guests.find_one({
        'email': current_user.email,
        'tenant_id': current_user.tenant_id
    })

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
