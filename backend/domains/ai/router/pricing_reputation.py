"""
pricing_reputation

Auto-split sub-router (shared imports/classes inlined).
"""

"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pydantic import Field as _PydField

from core.audit import log_audit_event
from core.database import db
from core.helpers import (
    require_module,
)
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


class ReviewIngest(BaseModel):
    platform: str = Field(min_length=2, max_length=60)
    external_id: str | None = Field(default=None, max_length=200)
    author_name: str | None = Field(default=None, max_length=160)
    review_text: str = Field(min_length=1, max_length=10000)
    rating: float = Field(ge=0, le=10)
    rating_scale: int = Field(default=5, ge=1, le=10)
    review_date: datetime | None = None


class ReviewResponseSuggestion(BaseModel):
    review_text: str = Field(min_length=1, max_length=10000)
    rating: float = Field(default=3, ge=0, le=10)


class ReviewResponseSave(BaseModel):
    response_text: str = Field(min_length=3, max_length=10000)


# ── GET /pricing/ai-recommendation ──
@router.get("/pricing/ai-recommendation")
@cached(ttl=300, key_prefix="ai_pricing_rec")
async def get_ai_pricing_recommendation(
    room_type: str | None = None,
    target_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("ai_pricing")),
    _perm=Depends(require_op("view_finance_reports")),  # v86 DV: AI pricing recommendation
):
    """AI-powered dynamic pricing recommendation"""
    try:
        # Default values when params not provided
        if not room_type:
            room_type = "standard"
        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        from domains.ai.dynamic_pricing_engine import get_pricing_engine

        engine = get_pricing_engine(db)
        recommendation = await engine.recommend_price(current_user.tenant_id, room_type, target_date)
        return recommendation
    except Exception:
        # Fail-closed: beklenmeyen bir hatada uydurma taban fiyat (eski sabit 150)
        # ile sahte oneri DONULMEZ. Durust "veri yok" yaniti verilir.
        logger.exception("ai-recommendation hesaplanamadi")
        return {
            "room_type": room_type,
            "target_date": target_date,
            "recommended_price": None,
            "min_price": None,
            "max_price": None,
            "current_price": None,
            "price_change_pct": None,
            "pricing_method": "unavailable",
            "applied_rules": ["Fiyat onerisi su anda uretilemiyor"],
            "competitor_data": {
                "available": False,
                "competitors": {},
                "average": None,
                "min": None,
                "max": None,
            },
            "demand_factors": None,
            "data_available": False,
            "source": "unavailable",
        }


# ── GET /pricing/competitor-rates ──
@router.get("/pricing/competitor-rates")
async def get_competitor_rates(room_type: str, target_date: str, current_user: User = Depends(get_current_user)):
    """Rakip otel fiyatları (yalnızca gerçek competitor_rates kayıtları)"""
    from domains.ai.dynamic_pricing_engine import get_pricing_engine

    engine = get_pricing_engine(db)
    rates = await engine.get_competitor_rates(current_user.tenant_id, target_date, room_type)

    return rates


# ── GET /reputation/overview ──
@router.get("/reputation/overview")
async def get_reputation_overview(current_user: User = Depends(get_current_user)):
    """Online reputation özeti"""
    from domains.ai.reputation_manager import get_reputation_manager

    manager = get_reputation_manager(db)
    overview = await manager.aggregate_reviews(current_user.tenant_id)

    return overview


@router.get("/reputation/reviews")
async def list_reputation_reviews(
    platform: str | None = None,
    response_status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    query = {"tenant_id": current_user.tenant_id}
    if platform:
        query["platform"] = platform
    if response_status:
        query["response_status"] = response_status
    reviews = await db.external_reviews.find(query, {"_id": 0}).sort("review_date", -1).to_list(limit)
    return {"reviews": reviews, "total": len(reviews)}


@router.post("/reputation/reviews", status_code=201)
async def ingest_reputation_review(
    body: ReviewIngest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    if body.rating > body.rating_scale:
        raise HTTPException(422, "Puan, puan ölçeğinden büyük olamaz")
    if body.external_id:
        duplicate = await db.external_reviews.find_one(
            {"tenant_id": current_user.tenant_id, "platform": body.platform.lower(), "external_id": body.external_id}
        )
        if duplicate:
            raise HTTPException(409, "Bu dış değerlendirme zaten kayıtlı")
    now = datetime.now(UTC).isoformat()
    review = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(mode="json"),
        "platform": body.platform.strip().lower(),
        "rating_5": round(body.rating * 5 / body.rating_scale, 2),
        "review_date": (body.review_date or datetime.now(UTC)).isoformat(),
        "received_at": now,
        "response_status": "pending",
        "source": "manual_import",
        "created_by": current_user.id,
    }
    await db.external_reviews.insert_one(review.copy())
    return {key: value for key, value in review.items() if key != "tenant_id"}


# ── GET /reputation/trends ──
@router.get("/reputation/trends")
async def get_reputation_trends(days: int = 30, current_user: User = Depends(get_current_user)):
    """Reputation trend analizi"""
    from domains.ai.reputation_manager import get_reputation_manager

    manager = get_reputation_manager(db)
    trends = await manager.get_reputation_trends(current_user.tenant_id, days)

    return trends


# ── POST /reputation/suggest-response ──
@router.post("/reputation/suggest-response")
async def suggest_review_response(
    review_data: ReviewResponseSuggestion,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """AI review yanıt önerisi"""
    from domains.ai.reputation_manager import get_reputation_manager

    manager = get_reputation_manager(db)
    sentiment = await manager.analyze_sentiment(review_data.review_text)
    response = await manager.suggest_response(review_data.review_text, review_data.rating)

    return {"suggested_response": response, "sentiment": sentiment, "generator": "rule_based_v1"}


@router.post("/reputation/reviews/{review_id}/response")
async def save_review_response(
    review_id: str,
    body: ReviewResponseSave,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    query = {"id": review_id, "tenant_id": current_user.tenant_id}
    review = await db.external_reviews.find_one(query, {"_id": 0})
    if not review:
        raise HTTPException(404, "Değerlendirme bulunamadı")
    now = datetime.now(UTC).isoformat()
    changes = {
        "response_text": body.response_text.strip(),
        "response_status": "responded",
        "responded_at": now,
        "responded_by": current_user.id,
        "provider_sync_status": "not_requested",
    }
    await db.external_reviews.update_one(query, {"$set": changes})
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="reputation.response.saved",
        entity_type="external_review",
        entity_id=review_id,
        details=f"{review.get('platform', 'external')} değerlendirmesi için yanıt kaydedildi",
        before_value={"response_status": review.get("response_status")},
        after_value=changes,
        db=db,
    )
    return {
        "success": True,
        "review_id": review_id,
        "response_status": "responded",
        "provider_write": False,
        "message": "Yanıt Syroce içinde kaydedildi; platforma otomatik gönderilmedi.",
    }


# ── GET /reputation/negative-alerts ──
@router.get("/reputation/negative-alerts")
async def get_negative_review_alerts(current_user: User = Depends(get_current_user)):
    """Son 24 saatteki negatif review'lar"""
    from domains.ai.reputation_manager import get_reputation_manager

    manager = get_reputation_manager(db)
    alerts = await manager.detect_negative_reviews(current_user.tenant_id)

    return {"negative_reviews": alerts, "total": len(alerts), "requires_action": len(alerts) > 0}
