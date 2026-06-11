"""
crm_guest

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
import re
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


# ── GET /crm/guest/{guest_id} ──
@router.get("/crm/guest/{guest_id}")
async def get_guest_360(
    guest_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get 360° guest profile with all data"""
    # Get guest basic info
    from security.encrypted_lookup import decrypt_guest_doc
    guest = decrypt_guest_doc(await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}))

    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    # Get all bookings
    bookings = await db.bookings.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('check_in', -1).to_list(100)

    # Calculate stats
    total_stays = len([b for b in bookings if b['status'] in ['checked_out', 'checked_in']])
    total_nights = 0
    lifetime_value = 0.0
    adr_values = []

    for booking in bookings:
        if booking['status'] in ['checked_out', 'checked_in', 'confirmed']:
            nights = (datetime.fromisoformat(booking['check_out']) - datetime.fromisoformat(booking['check_in'])).days
            total_nights += nights
            lifetime_value += booking.get('total_amount', 0)
            if nights > 0:
                adr_values.append(booking.get('total_amount', 0) / nights)

    average_adr = sum(adr_values) / len(adr_values) if adr_values else 0

    # Get preferences
    preferences = await db.guest_preferences.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    # Get behavior
    behavior = await db.guest_behavior.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    # Get profile or create one
    profile = await db.guest_profiles.find_one({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not profile:
        # Create profile
        profile = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'guest_id': guest_id,
            'first_name': guest.get('name', '').split()[0] if guest.get('name') else '',
            'last_name': ' '.join(guest.get('name', '').split()[1:]) if guest.get('name') and len(guest.get('name', '').split()) > 1 else '',
            'email': guest.get('email'),
            'phone': guest.get('phone'),
            'country': guest.get('country'),
            'total_stays': total_stays,
            'total_nights': total_nights,
            'lifetime_value': round(lifetime_value, 2),
            'average_adr': round(average_adr, 2),
            'loyalty_status': guest.get('loyalty_tier', 'standard'),
            'last_seen_date': bookings[0]['check_in'] if bookings else None,
            'tags': guest.get('tags', []),
            'notes': guest.get('notes', []),
            'created_at': datetime.now(UTC).isoformat(),
            'updated_at': datetime.now(UTC).isoformat()
        }
        await db.guest_profiles.insert_one(profile)

    # Channel distribution
    channel_mix = {}
    for booking in bookings:
        channel = booking.get('ota_channel') or 'direct'
        channel_mix[channel] = channel_mix.get(channel, 0) + 1

    # Recent upsells
    upsell_offers = await db.upsell_offers.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('created_at', -1).to_list(10)

    return {
        'guest': guest,
        'profile': profile,
        'preferences': preferences,
        'behavior': behavior,
        'stats': {
            'total_stays': total_stays,
            'total_nights': total_nights,
            'lifetime_value': round(lifetime_value, 2),
            'average_adr': round(average_adr, 2),
            'channel_distribution': channel_mix
        },
        'recent_bookings': bookings[:10],
        'recent_upsells': upsell_offers
    }
# ── POST /crm/guest/add-tag ──
@router.post("/crm/guest/add-tag")
async def add_guest_tag(
    guest_id: str,
    tag: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Add tag to guest"""
    result = await db.guests.update_one(
        {'id': guest_id, 'tenant_id': current_user.tenant_id},
        {'$addToSet': {'tags': tag}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Guest not found")

    return {'message': f'Tag "{tag}" added successfully'}
# ── POST /crm/guest/note ──
@router.post("/crm/guest/note")
async def add_guest_note(
    guest_id: str,
    note: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Add note to guest"""
    note_obj = {
        'text': note,
        'created_by': current_user.name,
        'created_at': datetime.now(UTC).isoformat()
    }

    result = await db.guests.update_one(
        {'id': guest_id, 'tenant_id': current_user.tenant_id},
        {'$push': {'notes': note_obj}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Guest not found")

    return {'message': 'Note added successfully', 'note': note_obj}
# ── DELETE /crm/guest/note ──
@router.delete("/crm/guest/note")
async def delete_guest_note(
    guest_id: str,
    note_index: int,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    guest = await db.guests.find_one({'id': guest_id, 'tenant_id': current_user.tenant_id})
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    notes = guest.get('notes', [])
    if note_index < 0 or note_index >= len(notes):
        raise HTTPException(status_code=400, detail="Invalid note index")
    notes.pop(note_index)
    await db.guests.update_one(
        {'id': guest_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'notes': notes}}
    )
    return {'message': 'Note deleted successfully'}
