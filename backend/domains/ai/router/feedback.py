"""
feedback

Auto-split sub-router (shared imports/classes inlined).
"""

"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pydantic import Field as _PydField

from core.database import db
from core.security import (
    get_current_user,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)


class GuestPersona(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__("uuid").uuid4().hex)
    tenant_id: str
    guest_id: str
    persona_type: str
    confidence_score: float
    indicators: list[str] = []
    recommendations: list[str] = []
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


class MaintenanceAlert(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__("uuid").uuid4().hex)
    tenant_id: str
    room_id: str
    equipment_type: str
    severity: str
    prediction: str
    indicators: list[str] = []
    recommended_action: str
    estimated_failure_days: int = 0
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


async def create_predictive_maintenance_task(tenant_id: str, room_id: str, room_number: str, title: str, severity: str, alert_id: str) -> None:
    try:
        await db.maintenance_tasks.insert_one(
            {
                "id": uuid.uuid4().hex,
                "tenant_id": tenant_id,
                "room_id": room_id,
                "room_number": room_number,
                "title": title,
                "severity": severity,
                "source_alert_id": alert_id,
                "status": "pending",
                "source": "predictive_ai",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    except Exception:
        logger.exception("[ai] failed to create predictive maintenance task")


def distribute_tasks(rooms: list[dict], staff: list[dict], task_type: str) -> list[dict]:
    """Round-robin task distribution across staff members."""
    if not staff:
        return []
    minutes_per_task = 30 if task_type == "checkout" else 20
    out = []
    for idx, room in enumerate(rooms):
        member = staff[idx % len(staff)]
        out.append(
            {
                "staff_id": member.get("id") or member.get("staff_id"),
                "staff_name": member.get("name") or member.get("staff_name") or "Staff",
                "task": {
                    "room_id": room.get("id") or room.get("room_id"),
                    "type": task_type,
                    "priority": "high" if task_type == "checkout" else "normal",
                    "estimated_minutes": minutes_per_task,
                },
                "estimated_minutes": minutes_per_task,
            }
        )
    return out


def generate_scheduling_recommendations(capacity_pct: float, staff_count: int, total_rooms: int) -> list[str]:
    recs = []
    if capacity_pct >= 110:
        recs.append("Schedule additional housekeeping staff or extend shifts.")
    elif capacity_pct >= 90:
        recs.append("Capacity is tight — monitor task completion closely.")
    else:
        recs.append("Workload is healthy.")
    if staff_count and total_rooms / max(staff_count, 1) > 18:
        recs.append("Consider rebalancing room-to-staff ratio.")
    return recs


def get_tier_benefits(tier: str) -> list[str]:
    matrix = {
        "silver": ["Welcome drink", "Late checkout 1h"],
        "gold": ["Room upgrade subject to availability", "Late checkout 2h", "10% F&B discount"],
        "platinum": ["Guaranteed upgrade", "Late checkout 4h", "20% F&B discount", "Lounge access"],
    }
    return matrix.get((tier or "").lower(), [])


logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


# ============= AI DYNAMIC PRICING (MARKET LEADER FEATURE) =============


# ============= WHATSAPP BUSINESS INTEGRATION =============


# ============= HOUSEKEEPING AI PREDICTIONS =============


# ============= PREDICTIVE ANALYTICS (GAME-CHANGER #2) =============


# ============= SOCIAL MEDIA COMMAND CENTER (GAME-CHANGER #3) =============


# ============= REVENUE AUTOPILOT (GAME-CHANGER #4) =============


# ============= GUEST DNA PROFILE (GAME-CHANGER #5) =============


# ============= DYNAMIC STAFFING AI (GAME-CHANGER #6) =============


# ============= DELUXE+ ENTERPRISE FEATURES =============


# ============= MAINTENANCE WORK ORDERS =============


# ============= LOYALTY PROGRAM ENHANCEMENTS =============


# ============= AI HOUSEKEEPING SCHEDULER =============


# ============= MONITORING & LOGGING ENDPOINTS =============


# ============= NEW ENHANCEMENTS: OTA, GUEST PROFILE, HK MOBILE, RMS, MESSAGING, POS =============

# ===== 1. OTA RESERVATION DETAILS ENHANCEMENTS =====

# Extra charges model
# Multi-room reservation tracking

router = APIRouter(prefix="/api", tags=["AI / ML"])


# ── POST /feedback/auto-reply ──
@router.post("/feedback/auto-reply")
async def generate_auto_reply(
    review_id: str,
    template_type: str = "standard",  # standard, apology, thank_you
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """
    Generate auto-reply for reviews using templates
    - Thank you for positive reviews
    - Apology for negative reviews
    - Customizable templates
    """
    review = await db.external_reviews.find_one({"id": review_id, "tenant_id": current_user.tenant_id})

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    guest_name = review.get("guest_name", "Guest")
    sentiment = review.get("sentiment", "neutral")

    # Generate reply based on sentiment
    if sentiment == "positive" or template_type == "thank_you":
        reply = f"Dear {guest_name},\n\nThank you for taking the time to share your wonderful feedback! We're thrilled to hear that you enjoyed your stay with us. Your kind words mean a lot to our team, and we look forward to welcoming you back soon.\n\nWarm regards,\n{current_user.name}\nGuest Relations Manager"

    elif sentiment == "negative" or template_type == "apology":
        reply = f"Dear {guest_name},\n\nThank you for sharing your feedback with us. We sincerely apologize that your experience did not meet your expectations. Your comments are very important to us, and we are taking immediate steps to address the issues you've raised.\n\nWe would appreciate the opportunity to discuss this further and make things right. Please contact me directly at your convenience.\n\nSincerely,\n{current_user.name}\nGuest Relations Manager"

    else:
        reply = f"Dear {guest_name},\n\nThank you for your feedback regarding your recent stay. We appreciate you taking the time to share your thoughts with us. Your input helps us continuously improve our services.\n\nWe hope to have the pleasure of welcoming you back in the future.\n\nBest regards,\n{current_user.name}\nGuest Relations Manager"

    return {"review_id": review_id, "generated_reply": reply, "template_type": template_type, "sentiment": sentiment, "can_edit": True, "note": "Review and edit before sending"}


# ── GET /feedback/source-filtering ──
@router.get("/feedback/source-filtering")
async def get_reviews_by_source(
    source: str,  # google, booking, tripadvisor, in_house
    days: int = 30,
    sentiment: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """
    Filter reviews by source
    - Google Reviews
    - Booking.com
    - TripAdvisor
    - In-house surveys
    """
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    match_criteria = {"tenant_id": current_user.tenant_id, "created_at": {"$gte": start_dt.isoformat(), "$lte": end_dt.isoformat()}}

    # Determine collection based on source
    if source == "in_house":
        collection = db.survey_responses
        match_criteria.pop("created_at")
        match_criteria["submitted_at"] = {"$gte": start_dt.isoformat(), "$lte": end_dt.isoformat()}
    else:
        collection = db.external_reviews
        match_criteria["platform"] = source

    if sentiment:
        match_criteria["sentiment"] = sentiment

    reviews = []
    async for review in collection.find(match_criteria).sort("created_at", -1):
        reviews.append(
            {
                "id": review.get("id"),
                "guest_name": review.get("guest_name"),
                "rating": review.get("rating") or review.get("overall_rating"),
                "review_text": review.get("review_text") or review.get("comments"),
                "sentiment": review.get("sentiment"),
                "date": review.get("created_at") or review.get("submitted_at"),
                "source": source,
            }
        )

    # Calculate summary
    total_reviews = len(reviews)
    avg_rating = sum(r["rating"] for r in reviews) / total_reviews if total_reviews > 0 else 0

    return {"source": source, "period_days": days, "sentiment_filter": sentiment, "total_reviews": total_reviews, "avg_rating": round(avg_rating, 2), "reviews": reviews}
