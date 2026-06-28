"""
rms

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from models.schemas import (
    RMSSuggestion,
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
    "early_checkin",
    "late_checkout",
    "airport_transfer",
    "room_upgrade",
    "spa_package",
    "dining_credit",
    "champagne",
    "custom",
}


async def check_rate_limit(tenant_id: str, channel: str, limit_per_hour: int = 100) -> bool:
    """Check if rate limit is exceeded for messaging"""
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    count = await db.messages.count_documents({"tenant_id": tenant_id, "channel": channel, "sent_at": {"$gte": one_hour_ago}})

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


# ── POST /rms/generate-suggestions ──
@router.post("/rms/generate-suggestions")
async def generate_rms_suggestions(
    start_date: str,
    end_date: str,
    room_type: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v100 DW
):
    """Generate RMS rate suggestions based on occupancy and demand"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    # Get all rooms or specific room type
    room_query = {"tenant_id": current_user.tenant_id}
    if room_type:
        room_query["room_type"] = room_type

    rooms = await db.rooms.find(room_query, {"_id": 0}).to_list(1000)
    room_types = list({r["room_type"] for r in rooms})

    suggestions = []

    for rt in room_types:
        rt_rooms = [r for r in rooms if r["room_type"] == rt]
        total_rooms = len(rt_rooms)

        # For each date in range
        current_date = start
        while current_date <= end:
            date_str = current_date.isoformat()

            # Calculate occupancy for this date
            start_of_day = datetime.combine(current_date, datetime.min.time())
            end_of_day = datetime.combine(current_date, datetime.max.time())

            bookings = await db.bookings.count_documents(
                {
                    "tenant_id": current_user.tenant_id,
                    "room_id": {"$in": [r["id"] for r in rt_rooms]},
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
                    "check_in": {"$lte": end_of_day.isoformat()},
                    "check_out": {"$gte": start_of_day.isoformat()},
                }
            )

            occupancy_rate = (bookings / total_rooms * 100) if total_rooms > 0 else 0

            # Get current rate (or use base rate)
            base_rate = rt_rooms[0].get("base_price", 100)

            # Simple dynamic pricing logic
            if occupancy_rate >= 90:
                suggested_rate = base_rate * 1.3  # +30%
                reason = "Very high demand (90%+ occupancy)"
                confidence = 95
            elif occupancy_rate >= 75:
                suggested_rate = base_rate * 1.2  # +20%
                reason = "High demand (75%+ occupancy)"
                confidence = 85
            elif occupancy_rate >= 60:
                suggested_rate = base_rate * 1.1  # +10%
                reason = "Good demand (60%+ occupancy)"
                confidence = 75
            elif occupancy_rate <= 30:
                suggested_rate = base_rate * 0.85  # -15%
                reason = "Low demand (< 30% occupancy)"
                confidence = 80
            else:
                suggested_rate = base_rate
                reason = "Normal demand (30-60% occupancy)"
                confidence = 60

            # Create suggestion
            suggestion = RMSSuggestion(
                tenant_id=current_user.tenant_id,
                date=date_str,
                room_type=rt,
                current_rate=base_rate,
                suggested_rate=round(suggested_rate, 2),
                reason=reason,
                confidence_score=confidence,
                based_on={"occupancy_rate": round(occupancy_rate, 2), "bookings": bookings, "total_rooms": total_rooms},
            )

            sugg_dict = suggestion.model_dump()
            sugg_dict["created_at"] = sugg_dict["created_at"].isoformat()
            await db.rms_suggestions.insert_one(sugg_dict)

            suggestions.append(suggestion)

            current_date += timedelta(days=1)

    return {
        "message": f"Generated {len(suggestions)} rate suggestions",
        "suggestions": suggestions[:20],  # Return first 20
        "total_count": len(suggestions),
    }


# ── GET /rms/suggestions ──
@router.get("/rms/suggestions")
async def get_rms_suggestions(status: str | None = None, date: str | None = None, room_type: str | None = None, current_user: User = Depends(get_current_user)):
    """Get RMS suggestions with filters"""
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    if date:
        query["date"] = date
    if room_type:
        query["room_type"] = room_type

    suggestions = await db.rms_suggestions.find(query, {"_id": 0}).sort("date", 1).to_list(100)
    return {"suggestions": suggestions, "count": len(suggestions)}


# ── POST /rms/apply-suggestion/{suggestion_id} ──
@router.post("/rms/apply-suggestion/{suggestion_id}")
async def apply_rms_suggestion(
    suggestion_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v100 DW
):
    """Apply RMS suggestion to room rates"""
    suggestion = await db.rms_suggestions.find_one({"id": suggestion_id, "tenant_id": current_user.tenant_id})

    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if suggestion["status"] == "applied":
        raise HTTPException(status_code=400, detail="Suggestion already applied")

    # Update rooms of this type with new rate
    await db.rooms.update_many({"tenant_id": current_user.tenant_id, "room_type": suggestion["room_type"]}, {"$set": {"base_price": suggestion["suggested_rate"]}})

    # Mark suggestion as applied
    await db.rms_suggestions.update_one({"id": suggestion_id}, {"$set": {"status": "applied"}})

    # Audit log
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="APPLY_RMS_SUGGESTION",
        entity_type="rms_suggestion",
        entity_id=suggestion_id,
        changes={"old_rate": suggestion["current_rate"], "new_rate": suggestion["suggested_rate"], "room_type": suggestion["room_type"]},
    )

    return {"message": f"Applied rate suggestion: {suggestion['room_type']} → ${suggestion['suggested_rate']}", "room_type": suggestion["room_type"], "new_rate": suggestion["suggested_rate"]}
