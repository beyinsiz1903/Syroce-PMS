"""
concierge_social

Auto-split sub-router (shared imports/classes inlined).
"""

"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
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


class SocialAutomationRuleIn(BaseModel):
    name: str = _PydField(min_length=1, max_length=120)
    keywords: list[str] = _PydField(min_length=1, max_length=30)
    reply: str = _PydField(min_length=1, max_length=2000)
    active: bool = True


def _social_rule_payload(payload: SocialAutomationRuleIn) -> dict:
    name = payload.name.strip()
    reply = payload.reply.strip()
    keywords = list(dict.fromkeys(keyword.strip().lower() for keyword in payload.keywords if keyword.strip()))
    if not name or not reply or not keywords:
        raise HTTPException(status_code=422, detail="Kural adı, en az bir anahtar kelime ve yanıt zorunludur")
    return {"name": name, "keywords": keywords, "reply": reply, "active": payload.active}


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


# ── POST /ai-concierge/whatsapp ──
@router.post("/ai-concierge/whatsapp")
async def ai_whatsapp_concierge(
    message_data: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("ai_whatsapp")),
):
    """AI WhatsApp Concierge - otomatik misafir yanıtı.

    Fail-closed: gerçek bir AI yanıt motoru (LLM) yapılandırılmadığı için
    sabit/sahte yanıt üretilmez. Gelen mesaj kaydedilir, ai_response boş kalır.
    """
    # Support both phone and guest_phone
    phone = message_data.get("phone") or message_data.get("guest_phone")
    message = message_data.get("message", "")

    # Gelen mesajı kaydet (yanıt üretilemedi)
    conversation = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "phone": phone,
        "user_message": message,
        "ai_response": None,
        "action_taken": None,
        "answered": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.ai_conversations.insert_one(conversation)

    return {
        "response": None,
        "action": None,
        "data_available": False,
        "message": "AI yanıt motoru (LLM) yapılandırılmamış. Otomatik yanıt üretilemedi.",
    }


# ── GET /ai-concierge/conversations ──
@router.get("/ai-concierge/conversations")
async def get_ai_conversations(phone: str | None = None, current_user: User = Depends(get_current_user)):
    """AI Concierge conversation history"""
    query = {"tenant_id": current_user.tenant_id}
    if phone:
        query["phone"] = phone

    conversations = await db.ai_conversations.find(query, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)

    return {"conversations": conversations, "total": len(conversations)}


# ── GET /social-media/mentions ──
@router.get("/social-media/mentions")
async def get_social_mentions(hours: int = 24, current_user: User = Depends(get_current_user)):
    """Son 24 saatteki social media mentions"""
    from domains.ai.social_media_radar import get_social_radar

    radar = get_social_radar(db)
    mentions = await radar.scan_mentions(current_user.tenant_id, hours)
    return {
        "mentions": mentions,
        "total": len(mentions),
        "data_available": False,
        "message": "Sosyal medya entegrasyonu yapılandırılmamış. Veri yok.",
    }


# ── GET /social-media/sentiment ──
@router.get("/social-media/sentiment")
async def get_sentiment_summary(days: int = 7, current_user: User = Depends(get_current_user)):
    """Sentiment özeti"""
    from domains.ai.social_media_radar import get_social_radar

    radar = get_social_radar(db)
    summary = await radar.get_sentiment_summary(current_user.tenant_id, days)
    return summary


# ── GET /social-media/crisis-alerts ──
@router.get("/social-media/crisis-alerts")
async def get_crisis_alerts(current_user: User = Depends(get_current_user)):
    """Kriz uyarıları"""
    from domains.ai.social_media_radar import get_social_radar

    radar = get_social_radar(db)
    alerts = await radar.detect_crisis(current_user.tenant_id)
    return {
        "alerts": alerts,
        "crisis_detected": len(alerts) > 0,
        "data_available": False,
        "message": "Sosyal medya entegrasyonu yapılandırılmamış. Veri yok.",
    }


@router.get("/social-media/automation-rules")
async def list_social_automation_rules(current_user: User = Depends(get_current_user)):
    rules = await db.social_automation_rules.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return rules


@router.post("/social-media/automation-rules", status_code=status.HTTP_201_CREATED)
async def create_social_automation_rule(
    payload: SocialAutomationRuleIn,
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(UTC).isoformat()
    rule = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **_social_rule_payload(payload),
        "created_at": now,
        "updated_at": now,
        "updated_by": current_user.id,
    }
    await db.social_automation_rules.insert_one(rule)
    return {key: value for key, value in rule.items() if key != "_id"}


@router.put("/social-media/automation-rules/{rule_id}")
async def update_social_automation_rule(
    rule_id: str,
    payload: SocialAutomationRuleIn,
    current_user: User = Depends(get_current_user),
):
    query = {"id": rule_id, "tenant_id": current_user.tenant_id}
    if not await db.social_automation_rules.find_one(query, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Otomasyon kuralı bulunamadı")
    updates = {
        **_social_rule_payload(payload),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": current_user.id,
    }
    await db.social_automation_rules.update_one(query, {"$set": updates})
    return await db.social_automation_rules.find_one(query, {"_id": 0})


@router.delete("/social-media/automation-rules/{rule_id}")
async def delete_social_automation_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    result = await db.social_automation_rules.delete_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Otomasyon kuralı bulunamadı")
    return {"deleted": True, "id": rule_id}
