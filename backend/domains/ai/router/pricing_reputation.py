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

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pydantic import Field as _PydField

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
    id: str = _PydField(default_factory=lambda: __import__('uuid').uuid4().hex)
    tenant_id: str
    guest_id: str
    persona_type: str
    confidence_score: float
    indicators: list[str] = []
    recommendations: list[str] = []
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


class MaintenanceAlert(BaseModel):
    id: str = _PydField(default_factory=lambda: __import__('uuid').uuid4().hex)
    tenant_id: str
    room_id: str
    equipment_type: str
    severity: str
    prediction: str
    indicators: list[str] = []
    recommended_action: str
    estimated_failure_days: int = 0
    created_at: datetime = _PydField(default_factory=lambda: datetime.now(UTC))


async def create_predictive_maintenance_task(
    tenant_id: str, room_id: str, room_number: str, title: str, severity: str, alert_id: str
) -> None:
    try:
        await db.maintenance_tasks.insert_one({
            'id': uuid.uuid4().hex,
            'tenant_id': tenant_id,
            'room_id': room_id,
            'room_number': room_number,
            'title': title,
            'severity': severity,
            'source_alert_id': alert_id,
            'status': 'pending',
            'source': 'predictive_ai',
            'created_at': datetime.now(UTC).isoformat(),
        })
    except Exception:
        logger.exception('[ai] failed to create predictive maintenance task')


def distribute_tasks(rooms: list[dict], staff: list[dict], task_type: str) -> list[dict]:
    """Round-robin task distribution across staff members."""
    if not staff:
        return []
    minutes_per_task = 30 if task_type == 'checkout' else 20
    out = []
    for idx, room in enumerate(rooms):
        member = staff[idx % len(staff)]
        out.append({
            'staff_id': member.get('id') or member.get('staff_id'),
            'staff_name': member.get('name') or member.get('staff_name') or 'Staff',
            'task': {
                'room_id': room.get('id') or room.get('room_id'),
                'type': task_type,
                'priority': 'high' if task_type == 'checkout' else 'normal',
                'estimated_minutes': minutes_per_task,
            },
            'estimated_minutes': minutes_per_task,
        })
    return out


def generate_scheduling_recommendations(capacity_pct: float, staff_count: int, total_rooms: int) -> list[str]:
    recs = []
    if capacity_pct >= 110:
        recs.append('Schedule additional housekeeping staff or extend shifts.')
    elif capacity_pct >= 90:
        recs.append('Capacity is tight — monitor task completion closely.')
    else:
        recs.append('Workload is healthy.')
    if staff_count and total_rooms / max(staff_count, 1) > 18:
        recs.append('Consider rebalancing room-to-staff ratio.')
    return recs


def get_tier_benefits(tier: str) -> list[str]:
    matrix = {
        'silver': ['Welcome drink', 'Late checkout 1h'],
        'gold': ['Room upgrade subject to availability', 'Late checkout 2h', '10% F&B discount'],
        'platinum': ['Guaranteed upgrade', 'Late checkout 4h', '20% F&B discount', 'Lounge access'],
    }
    return matrix.get((tier or '').lower(), [])


logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
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
        recommendation = await engine.recommend_price(
            current_user.tenant_id,
            room_type,
            target_date
        )
        return recommendation
    except Exception:
        # Fallback pricing recommendation
        rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}).to_list(None)
        bookings = await db.bookings.find({
            "tenant_id": current_user.tenant_id,
            "status": {"$in": ["confirmed", "checked_in"]}
        }).to_list(None)
        total_rooms = len(rooms) or 1
        occupied = len([b for b in bookings if b.get('status') == 'checked_in'])
        occupancy_rate = occupied / total_rooms

        base_price = 150
        if occupancy_rate > 0.8:
            suggested = base_price * 1.3
        elif occupancy_rate > 0.5:
            suggested = base_price * 1.1
        else:
            suggested = base_price * 0.9

        return {
            "recommended_rate": round(suggested, 2),
            "current_rate": base_price,
            "suggested_price": round(suggested, 2),
            "current_price": base_price,
            "confidence": round(0.7 + occupancy_rate * 0.2, 2),
            "reason": f"Doluluk oranı %{round(occupancy_rate*100)}, talebe göre fiyat önerisi",
            "room_type": room_type,
            "target_date": target_date,
            "source": "heuristic"
        }
# ── GET /pricing/competitor-rates ──
@router.get("/pricing/competitor-rates")
async def get_competitor_rates(
    room_type: str,
    target_date: str,
    current_user: User = Depends(get_current_user)
):
    """Rakip otel fiyatları"""
    from dynamic_pricing_engine import get_pricing_engine

    engine = get_pricing_engine(db)
    rates = await engine.get_competitor_rates(target_date, room_type)

    return rates
# ── GET /reputation/overview ──
@router.get("/reputation/overview")
async def get_reputation_overview(current_user: User = Depends(get_current_user)):
    """Online reputation özeti"""
    from domains.ai.reputation_manager import get_reputation_manager

    manager = get_reputation_manager(db)
    overview = await manager.aggregate_reviews(current_user.tenant_id)

    return overview
# ── GET /reputation/trends ──
@router.get("/reputation/trends")
async def get_reputation_trends(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """Reputation trend analizi"""
    from domains.ai.reputation_manager import get_reputation_manager

    manager = get_reputation_manager(db)
    trends = await manager.get_reputation_trends(current_user.tenant_id, days)

    return trends
# ── POST /reputation/suggest-response ──
@router.post("/reputation/suggest-response")
async def suggest_review_response(
    review_data: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    """AI review yanıt önerisi"""
    from domains.ai.reputation_manager import get_reputation_manager

    manager = get_reputation_manager(db)
    response = await manager.suggest_response(
        review_data['review_text'],
        review_data.get('rating', 3)
    )

    return {
        'suggested_response': response
    }
# ── GET /reputation/negative-alerts ──
@router.get("/reputation/negative-alerts")
async def get_negative_review_alerts(current_user: User = Depends(get_current_user)):
    """Son 24 saatteki negatif review'lar"""
    from domains.ai.reputation_manager import get_reputation_manager

    manager = get_reputation_manager(db)
    alerts = await manager.detect_negative_reviews(current_user.tenant_id)

    return {
        'negative_reviews': alerts,
        'total': len(alerts),
        'requires_action': len(alerts) > 0
    }
