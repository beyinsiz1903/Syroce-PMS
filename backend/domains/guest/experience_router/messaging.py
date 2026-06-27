"""
messaging

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import (
    User,
)
from modules.pms_core.role_permission_service import require_op  # v98 DW

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


# ── POST /messages/send-email ──
@router.post("/messages/send-email")
async def send_email(
    recipient: str,
    subject: str,
    body: str,
    guest_id: str | None = None,
    template_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Send email message with rate limiting"""
    # Check rate limit (100 emails per hour)
    if not await check_rate_limit(current_user.tenant_id, 'email', limit_per_hour=100):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 100 emails per hour. Please try again later."
        )

    # Validate email format
    if not recipient or '@' not in recipient:
        raise HTTPException(status_code=400, detail="Invalid email address")

    # Validate message body
    if not body or len(body.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    message = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'channel': 'email',
        'recipient': recipient,
        'subject': subject,
        'body': body,
        'template_id': template_id,
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id,
        'status': 'sent'
    }

    await db.messages.insert_one(message)

    return {
        'message': 'Email sent successfully',
        'message_id': message['id'],
        'recipient': recipient,
        'rate_limit': {
            'limit': 100,
            'window': '1 hour',
            'remaining': 100 - await db.messages.count_documents({
                'tenant_id': current_user.tenant_id,
                'channel': 'email',
                'sent_at': {'$gte': (datetime.now(UTC) - timedelta(hours=1)).isoformat()}
            })
        }
    }
# ── POST /messages/send-sms ──
@router.post("/messages/send-sms")
async def send_sms(
    recipient: str,
    body: str,
    guest_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Send SMS message with stricter rate limiting (50 per hour)"""
    # SMS has stricter rate limit due to cost
    if not await check_rate_limit(current_user.tenant_id, 'sms', limit_per_hour=50):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 50 SMS per hour. Please try again later."
        )

    # Validate phone number format
    if not recipient or not recipient.startswith('+'):
        raise HTTPException(status_code=400, detail="Invalid phone number format. Must start with + and country code")

    # Validate message body
    if not body or len(body.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    # Warn if message is too long for single SMS
    if len(body) > 160:
        message_warning = f"Message is {len(body)} characters. Will be sent as {(len(body) // 160) + 1} SMS segments."
    else:
        message_warning = None

    message = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'channel': 'sms',
        'recipient': recipient,
        'body': body,
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id,
        'status': 'sent',
        'character_count': len(body),
        'segment_count': (len(body) // 160) + 1
    }

    await db.messages.insert_one(message)

    response = {
        'message': 'SMS sent successfully',
        'message_id': message['id'],
        'recipient': recipient,
        'character_count': len(body),
        'segments': (len(body) // 160) + 1,
        'rate_limit': {
            'limit': 50,
            'window': '1 hour',
            'remaining': 50 - await db.messages.count_documents({
                'tenant_id': current_user.tenant_id,
                'channel': 'sms',
                'sent_at': {'$gte': (datetime.now(UTC) - timedelta(hours=1)).isoformat()}
            })
        }
    }

    if message_warning:
        response['warning'] = message_warning

    return response
# ── POST /messages/send-whatsapp ──
@router.post("/messages/send-whatsapp")
async def send_whatsapp(
    recipient: str,
    body: str,
    guest_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Send WhatsApp message with rate limiting (80 per hour)"""
    # WhatsApp rate limit
    if not await check_rate_limit(current_user.tenant_id, 'whatsapp', limit_per_hour=80):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 80 WhatsApp messages per hour. Please try again later."
        )

    # Validate phone number format
    if not recipient or not recipient.startswith('+'):
        raise HTTPException(status_code=400, detail="Invalid phone number format. Must start with + and country code")

    # Validate message body
    if not body or len(body.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    message = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'channel': 'whatsapp',
        'recipient': recipient,
        'body': body,
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.id,
        'status': 'sent',
        'character_count': len(body)
    }

    await db.messages.insert_one(message)

    return {
        'message': 'WhatsApp sent successfully',
        'message_id': message['id'],
        'recipient': recipient,
        'character_count': len(body),
        'rate_limit': {
            'limit': 80,
            'window': '1 hour',
            'remaining': 80 - await db.messages.count_documents({
                'tenant_id': current_user.tenant_id,
                'channel': 'whatsapp',
                'sent_at': {'$gte': (datetime.now(UTC) - timedelta(hours=1)).isoformat()}
            })
        }
    }
# ── GET /messages/templates ──
@router.get("/messages/templates")
async def get_message_templates(
    channel: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get message templates"""
    query = {'tenant_id': current_user.tenant_id, 'active': True}
    if channel:
        query['channel'] = channel

    templates = await db.message_templates.find(query, {'_id': 0}).to_list(100)
    return {'templates': templates, 'count': len(templates)}
