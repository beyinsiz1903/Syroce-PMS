"""
reviews

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

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


# ── GET /crm/reviews ──
@router.get("/crm/reviews")
async def get_reviews(
    current_user: User = Depends(get_current_user)
):
    """Get guest reviews"""
    reviews = await db.guest_reviews.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).sort('created_at', -1).to_list(1000)
    return {"reviews": reviews}
# ── POST /crm/reviews/{review_id}/respond ──
@router.post("/crm/reviews/{review_id}/respond")
async def respond_to_review(
    review_id: str,
    response_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """Respond to a guest review"""
    await db.guest_reviews.update_one(
        {'id': review_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'response': response_data.get('response'),
            'responded_at': datetime.now(UTC).isoformat(),
            'responded_by': current_user.id
        }}
    )
    return {"message": "Response sent successfully"}
