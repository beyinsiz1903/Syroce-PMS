"""
ops

Auto-split sub-router (shared imports/classes inlined).
"""

"""
AI / ML Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import os as _os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pydantic import Field as _PydField

from core.database import db
from core.security import (
    _is_super_admin,
    get_current_user,
)
from domains.ai.service import AIService as _AIService
from domains.ai.service import get_ai_llm_call_ledger as _get_ledger
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


# ── GET /staffing-ai/optimal ──
@router.get("/staffing-ai/optimal")
async def get_optimal_staffing(target_date: str = None, current_user: User = Depends(get_current_user)):
    """Get optimal staffing recommendations.

    Gercek personel/vardiya optimizasyon kaynagi (personel sayisi, vardiya
    planlama, is yuku tahmini) entegre degil. Uydurma oneri uretmek yerine
    fail-closed (data_available=False) doner.
    """
    return {
        "target_date": target_date or datetime.now().strftime("%Y-%m-%d"),
        "departments": {},
        "total_cost_savings": 0,
        "efficiency_gain": None,
        "data_available": False,
        "message": "Personel optimizasyon verisi mevcut degil. Vardiya/personel modulu yapilandirilmamis.",
    }


# ── GET /staffing-ai/schedule ──
@router.get("/staffing-ai/schedule")
async def generate_auto_schedule(target_date: str = None, current_user: User = Depends(get_current_user)):
    """Generate AI-optimized staff schedule.

    Gercek vardiya planlama kaynagi (personel listesi, musaitlik, is yuku)
    entegre degil. Uydurma plan uretmek yerine fail-closed doner.
    """
    return {
        "schedule": [],
        "target_date": target_date or datetime.now().strftime("%Y-%m-%d"),
        "optimization_score": None,
        "data_available": False,
        "message": "Otomatik vardiya plani icin veri mevcut degil.",
    }


# ── POST /ai/predictive-maintenance/analyze ──
@router.post("/ai/predictive-maintenance/analyze")
async def analyze_predictive_maintenance(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """
    Predictive Maintenance Analysis
    - IoT sensor data analysis (simulated)
    - Pattern detection
    - Failure prediction before breakdown
    - Automatic task assignment
    """
    # In production: Integrate with IoT sensors, HVAC controllers, BMS
    # Analyze: Temperature patterns, error codes, usage frequency, vibration data

    alerts = []

    # Get all rooms
    rooms = []
    async for room in db.rooms.find({"tenant_id": current_user.tenant_id}):
        rooms.append(room)

    # Get maintenance history
    for room in rooms:
        room_id = room.get("id")
        room_number = room.get("room_number")

        # Get past maintenance issues
        issues = []
        async for task in db.maintenance_tasks.find({"room_id": room_id, "tenant_id": current_user.tenant_id}).sort("created_at", -1).limit(10):
            issues.append(task)

        # Pattern Analysis (Simulated AI/ML)

        # 1. HVAC Analysis
        hvac_issues = [i for i in issues if "ac" in i.get("description", "").lower() or "hvac" in i.get("description", "").lower()]
        if len(hvac_issues) >= 2:
            # Recurring AC issues detected
            alert = MaintenanceAlert(
                tenant_id=current_user.tenant_id,
                room_id=room_id,
                equipment_type="hvac",
                severity="high",
                prediction=f"AC unit in room {room_number} showing recurring issue pattern",
                indicators=[
                    f"{len(hvac_issues)} AC/HVAC issue(s) recorded in maintenance history",
                ],
                recommended_action="Schedule preventive maintenance - compressor inspection",
                estimated_failure_days=0,
            )

            alert_dict = alert.model_dump()
            alert_dict["created_at"] = alert_dict["created_at"].isoformat()
            alert_dict["status"] = "pending"
            await db.predictive_maintenance_alerts.insert_one(alert_dict)
            alerts.append(alert_dict)

            # Auto-create maintenance task
            await create_predictive_maintenance_task(current_user.tenant_id, room_id, room_number, "Preventive HVAC Maintenance", "high", alert.id)

        # 2. Plumbing Analysis
        plumbing_issues = [i for i in issues if "leak" in i.get("description", "").lower() or "water" in i.get("description", "").lower()]
        if len(plumbing_issues) >= 1:
            alert = MaintenanceAlert(
                tenant_id=current_user.tenant_id,
                room_id=room_id,
                equipment_type="plumbing",
                severity="medium",
                prediction=f"Potential leak risk in room {room_number}",
                indicators=[
                    f"{len(plumbing_issues)} leak/water issue(s) recorded in maintenance history",
                ],
                recommended_action="Inspect pipes and seals",
                estimated_failure_days=0,
            )

            alert_dict = alert.model_dump()
            alert_dict["created_at"] = alert_dict["created_at"].isoformat()
            alert_dict["status"] = "pending"
            await db.predictive_maintenance_alerts.insert_one(alert_dict)
            alerts.append(alert_dict)

    return {
        "analysis_date": datetime.now().date().isoformat(),
        "rooms_analyzed": len(rooms),
        "alerts_generated": len(alerts),
        "high_priority": sum(1 for a in alerts if a.get("severity") == "high"),
        "medium_priority": sum(1 for a in alerts if a.get("severity") == "medium"),
        "alerts": alerts,
        "summary": f"{len(alerts)} potential failures predicted - proactive maintenance scheduled",
        # Gercek maliyet/tasarruf kaynagi entegre degil; uydurma rakam raporlanmaz.
        "cost_savings_estimate": None,
        "data_available": True,
    }


# ── GET /ai/predictive-maintenance/dashboard ──
@router.get("/ai/predictive-maintenance/dashboard")
async def get_predictive_maintenance_dashboard(current_user: User = Depends(get_current_user)):
    """Get predictive maintenance dashboard"""
    alerts = []
    async for alert in db.predictive_maintenance_alerts.find({"tenant_id": current_user.tenant_id, "status": "pending"}).sort("severity", -1):
        room = await db.rooms.find_one({"id": alert.get("room_id"), "tenant_id": current_user.tenant_id})
        alerts.append(
            {
                "alert_id": alert.get("id"),
                "room_number": room.get("room_number") if room else "Unknown",
                "equipment": alert.get("equipment_type"),
                "severity": alert.get("severity"),
                "prediction": alert.get("prediction"),
                "days_until_failure": alert.get("estimated_failure_days"),
                "recommended_action": alert.get("recommended_action"),
            }
        )

    return {"total_alerts": len(alerts), "critical_alerts": sum(1 for a in alerts if a["severity"] == "critical"), "alerts": alerts}


# ── POST /ai/housekeeping/smart-schedule ──
@router.post("/ai/housekeeping/smart-schedule")
async def ai_housekeeping_smart_scheduler(
    date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v99 DW
):
    """
    AI Housekeeping Scheduler
    - Occupancy forecast analysis
    - Available staff calculation
    - Intelligent task distribution
    - Workload balancing
    """
    datetime.fromisoformat(date)

    # 1. Get occupancy forecast
    occupied_rooms = []
    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": {"$lte": date}, "check_out": {"$gte": date}, "status": {"$in": ["confirmed", "checked_in"]}}):
        occupied_rooms.append({"room_id": booking.get("room_id")})

    # 2. Check-outs today (require deep cleaning)
    checkout_today = []
    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "check_out": date, "status": "checked_in"}):
        checkout_today.append({"room_id": booking.get("room_id")})

    # 3. Get available HK staff
    hk_staff = []
    async for user in db.users.find({"tenant_id": current_user.tenant_id, "role": "housekeeping", "status": "active"}):
        hk_staff.append(user)

    if not hk_staff:
        # Gercek aktif kat hizmetleri personeli yok: uydurma personel uretip
        # sahte gorev olusturmak yerine fail-closed don. Forecast alanlari
        # gercek rezervasyon verisinden gelir, korunur.
        total_rooms_to_clean = len(occupied_rooms) + len(checkout_today)
        return {
            "date": date,
            "data_available": False,
            "forecast": {
                "occupied_rooms": len(occupied_rooms),
                "checkout_rooms": len(checkout_today),
                "total_rooms_to_clean": total_rooms_to_clean,
            },
            "staffing": {
                "available_staff": 0,
                "total_available_hours": 0,
                "required_hours": 0,
                "capacity_utilization": 0,
                "status": "Personel yok",
            },
            "ai_schedule": {
                "tasks_per_staff": 0,
                "workload_balanced": False,
                "staff_assignments": [],
            },
            "recommendations": [
                "Aktif kat hizmetleri personeli bulunamadi; otomatik plan olusturulamadi.",
            ],
            "message": "Aktif kat hizmetleri personeli bulunamadigi icin otomatik plan olusturulamadi.",
        }

    staff_count = len(hk_staff)

    # 4. Calculate workload
    total_rooms = len(occupied_rooms) + len(checkout_today)

    # Standard cleaning times
    occupied_cleaning_time = 20  # minutes
    checkout_cleaning_time = 45  # minutes (deep clean)

    total_minutes = (len(occupied_rooms) * occupied_cleaning_time) + (len(checkout_today) * checkout_cleaning_time)

    # Available staff hours (8-hour shift = 480 minutes)
    available_minutes = staff_count * 480

    # AI Task Distribution
    tasks_per_staff = total_rooms / staff_count if staff_count > 0 else 0

    # Intelligent assignment (balance workload)
    staff_assignments = []

    # Priority 1: Checkout rooms (must be done first)
    checkout_assignments = distribute_tasks(checkout_today, hk_staff, "checkout")

    # Priority 2: Occupied rooms
    occupied_assignments = distribute_tasks(occupied_rooms, hk_staff, "occupied")

    # Combine assignments
    combined = {}
    for assignment in checkout_assignments + occupied_assignments:
        staff_name = assignment["staff_name"]
        if staff_name not in combined:
            combined[staff_name] = {"staff_name": staff_name, "staff_id": assignment["staff_id"], "tasks": [], "total_tasks": 0, "estimated_minutes": 0}
        combined[staff_name]["tasks"].append(assignment["task"])
        combined[staff_name]["total_tasks"] += 1
        combined[staff_name]["estimated_minutes"] += assignment["estimated_minutes"]

    staff_assignments = list(combined.values())

    # Create tasks in database
    for assignment in staff_assignments:
        for task in assignment["tasks"]:
            await db.housekeeping_tasks.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": current_user.tenant_id,
                    "room_id": task["room_id"],
                    "task_type": task["type"],
                    "priority": task["priority"],
                    "assigned_to": assignment["staff_name"],
                    "status": "pending",
                    "scheduled_date": date,
                    "estimated_duration": task["estimated_minutes"],
                    "created_at": datetime.now(UTC).isoformat(),
                    "source": "ai_scheduler",
                }
            )

    # Capacity analysis
    capacity_pct = (total_minutes / available_minutes * 100) if available_minutes > 0 else 0

    return {
        "date": date,
        "data_available": True,
        "forecast": {"occupied_rooms": len(occupied_rooms), "checkout_rooms": len(checkout_today), "total_rooms_to_clean": total_rooms},
        "staffing": {
            "available_staff": staff_count,
            "total_available_hours": available_minutes / 60,
            "required_hours": total_minutes / 60,
            "capacity_utilization": round(capacity_pct, 1),
            "status": "✅ Adequate" if capacity_pct < 90 else "⚠️ Tight" if capacity_pct < 110 else "🚨 Understaffed",
        },
        "ai_schedule": {"tasks_per_staff": round(tasks_per_staff, 1), "workload_balanced": True, "staff_assignments": staff_assignments},
        "recommendations": generate_scheduling_recommendations(capacity_pct, staff_count, total_rooms),
    }


# ── POST /ai/loyalty/auto-tier-upgrade ──
@router.post("/ai/loyalty/auto-tier-upgrade")
async def auto_loyalty_tier_upgrade(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    """
    Automatic Loyalty Tier Upgrade
    - Analyzes guest behavior patterns
    - OTA → Direct conversion: bonus points
    - Repeat visits: auto tier upgrade
    - Smart loyalty management
    """
    upgrades = []

    # Get all guests
    async for guest in db.guests.find({"tenant_id": current_user.tenant_id}):
        guest_id = guest.get("id")
        guest_name = guest.get("name")
        current_points = guest.get("loyalty_points", 0)
        current_tier = guest.get("loyalty_tier", "bronze")

        # Get booking history
        bookings = []
        async for booking in db.bookings.find({"guest_id": guest_id, "tenant_id": current_user.tenant_id}).sort("created_at", 1):
            bookings.append(booking)

        if not bookings:
            continue

        # Behavior Analysis
        ota_bookings = [b for b in bookings if b.get("channel") in ["booking_com", "expedia", "airbnb"]]
        direct_bookings = [b for b in bookings if b.get("channel") == "direct"]

        # Rule 1: OTA → Direct Conversion Bonus
        if len(ota_bookings) > 0 and len(direct_bookings) > 0:
            # Check if last booking was direct (conversion!)
            last_booking = bookings[-1]
            if last_booking.get("channel") == "direct":
                # Previous was OTA?
                if len(bookings) > 1 and bookings[-2].get("channel") in ["booking_com", "expedia", "airbnb"]:
                    # Conversion detected!
                    bonus_points = 500
                    new_points = current_points + bonus_points

                    await db.guests.update_one({"id": guest_id}, {"$set": {"loyalty_points": new_points}})

                    upgrades.append(
                        {
                            "guest_id": guest_id,
                            "guest_name": guest_name,
                            "action": "ota_to_direct_bonus",
                            "bonus_points": bonus_points,
                            "reason": "Switched from OTA to direct booking",
                            "old_points": current_points,
                            "new_points": new_points,
                        }
                    )

                    current_points = new_points  # Update for tier calculation

        # Rule 2: Repeat Visit Auto-Tier Upgrade
        if len(bookings) >= 3:  # 3+ stays
            # Calculate recommended tier
            if current_points >= 10000 and current_tier != "platinum":
                new_tier = "platinum"
            elif current_points >= 5000 and current_tier not in ["platinum", "gold"]:
                new_tier = "gold"
            elif current_points >= 1000 and current_tier not in ["platinum", "gold", "silver"]:
                new_tier = "silver"
            else:
                new_tier = current_tier

            if new_tier != current_tier:
                await db.guests.update_one({"id": guest_id}, {"$set": {"loyalty_tier": new_tier}})

                upgrades.append(
                    {
                        "guest_id": guest_id,
                        "guest_name": guest_name,
                        "action": "tier_upgrade",
                        "old_tier": current_tier,
                        "new_tier": new_tier,
                        "reason": f"{len(bookings)} stays, {current_points} points earned",
                        "benefits_unlocked": get_tier_benefits(new_tier),
                    }
                )

        # Rule 3: Frequency Bonus (Bookings within 90 days)
        if len(bookings) >= 2:
            last_two = bookings[-2:]
            if len(last_two) == 2:
                date1 = datetime.fromisoformat(last_two[0].get("check_out"))
                date2 = datetime.fromisoformat(last_two[1].get("check_in"))
                days_between = (date2 - date1).days

                if days_between <= 90:
                    frequency_bonus = 300
                    new_points = current_points + frequency_bonus

                    await db.guests.update_one({"id": guest_id}, {"$set": {"loyalty_points": new_points}})

                    upgrades.append(
                        {
                            "guest_id": guest_id,
                            "guest_name": guest_name,
                            "action": "frequency_bonus",
                            "bonus_points": frequency_bonus,
                            "reason": f"Repeat visit within {days_between} days",
                            "old_points": current_points,
                            "new_points": new_points,
                        }
                    )

    # Create notification alerts for upgrades
    for upgrade in upgrades:
        await db.alerts.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "alert_type": "loyalty_upgrade",
                "priority": "normal",
                "title": f"Loyalty upgrade: {upgrade['guest_name']}",
                "description": upgrade["reason"],
                "source_module": "loyalty_ai",
                "status": "unread",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    return {
        "analysis_date": datetime.now().date().isoformat(),
        "guests_analyzed": await db.guests.count_documents({"tenant_id": current_user.tenant_id}),
        "upgrades_applied": len(upgrades),
        "upgrades": upgrades,
        "summary": {
            "ota_conversions": sum(1 for u in upgrades if u["action"] == "ota_to_direct_bonus"),
            "tier_upgrades": sum(1 for u in upgrades if u["action"] == "tier_upgrade"),
            "frequency_bonuses": sum(1 for u in upgrades if u["action"] == "frequency_bonus"),
        },
    }


# ── GET /ai/diagnostics/llm-state ──
# F8O (Task #206) — AI/Automation dry-run vendor-call read-only probe.
# Returns whether the LLM provider surface is "enabled" (api key present in
# env) and which providers are configured. **Does NOT** issue any vendor
# HTTP call; pure config read so stress specs can verify isolation without
# triggering external traffic. RBAC: view_system_diagnostics (super_admin).
@router.get("/ai/diagnostics/llm-state")
async def get_ai_llm_state(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    # Strict super_admin gate (architect P1 review). require_op above also
    # permits admin role + explicit granted_permissions; this endpoint
    # exposes provider/env state and must be super_admin-only.
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="Super admin only")
    # Task #206 — diagnostics surface MUST be gated by E2E_AI_DRY_RUN=true.
    # Outside test mode the endpoint is fail-closed (503) so production
    # deployments cannot leak provider/env shape through this route.
    e2e_dry_run = (_os.getenv("E2E_AI_DRY_RUN") or "").lower() in ("1", "true", "yes", "on")
    if not e2e_dry_run:
        raise HTTPException(status_code=503, detail="AI diagnostics disabled (E2E_AI_DRY_RUN not set)")
    svc = _AIService()
    openai_key = _os.getenv("OPENAI_API_KEY")
    anthropic_key = _os.getenv("ANTHROPIC_API_KEY")
    gemini_key = _os.getenv("GEMINI_API_KEY") or _os.getenv("GOOGLE_API_KEY")

    def _looks_real(k: str | None) -> bool:
        if not k or not isinstance(k, str):
            return False
        # Production-shape prefixes for OpenAI / Anthropic / Google.
        return k.startswith("sk-ant-") or (k.startswith("sk-") and len(k) >= 30) or k.startswith("AIza")

    looks_like_real_key = any(_looks_real(k) for k in (openai_key, anthropic_key, gemini_key))

    # Vendor base-URL guard (Task #206 finding #1). If any LLM key is set
    # AND the corresponding base_url override either points to a known
    # real vendor host OR is unset (SDK default = real vendor host), the
    # process can egress to real OpenAI/Anthropic/Google endpoints. Stress
    # dry-run requires base_url to be overridden to a mock/sentinel target.
    openai_base = (_os.getenv("OPENAI_BASE_URL") or "").strip()
    anthropic_base = (_os.getenv("ANTHROPIC_BASE_URL") or "").strip()
    gemini_base = (_os.getenv("GEMINI_BASE_URL") or _os.getenv("GOOGLE_BASE_URL") or "").strip()
    REAL_VENDOR_HOSTS = (
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
    )

    def _url_is_real(url: str | None) -> bool:
        if not url:
            return False
        u = url.lower()
        return any(h in u for h in REAL_VENDOR_HOSTS)

    # Per-provider: if a key is configured for that provider, the base_url
    # must be (a) explicitly set AND (b) not pointing at a real vendor host.
    # Unset base_url with key set → SDK defaults to real host → P0.
    openai_url_real = bool(openai_key) and (not openai_base or _url_is_real(openai_base))
    anthropic_url_real = bool(anthropic_key) and (not anthropic_base or _url_is_real(anthropic_base))
    gemini_url_real = bool(gemini_key) and (not gemini_base or _url_is_real(gemini_base))
    looks_like_real_vendor_url = openai_url_real or anthropic_url_real or gemini_url_real

    ledger = _get_ledger()
    return {
        "llm_enabled": bool(getattr(svc, "llm_enabled", False)),
        "providers": {
            "openai_configured": bool(openai_key),
            "anthropic_configured": bool(anthropic_key),
            "gemini_configured": bool(gemini_key),
        },
        "looks_like_real_key": looks_like_real_key,
        "vendor_base_urls": {
            # Only emit set/unset bool — never the raw URL value to avoid
            # leaking deployment topology through diagnostics surface.
            "openai_base_url_set": bool(openai_base),
            "anthropic_base_url_set": bool(anthropic_base),
            "gemini_base_url_set": bool(gemini_base),
        },
        "looks_like_real_vendor_url": looks_like_real_vendor_url,
        "real_vendor_url_breakdown": {
            "openai": openai_url_real,
            "anthropic": anthropic_url_real,
            "gemini": gemini_url_real,
        },
        "e2e_ai_dry_run": e2e_dry_run,
        "e2e_external_dry_run": (_os.getenv("E2E_EXTERNAL_DRY_RUN") or "").lower() in ("1", "true", "yes", "on"),
        "attempted_call_count": int(ledger.get("attempted_count", 0)),
        "recent_attempts": ledger.get("last_attempts") or [],
        "model_name_default": "gpt-4o-mini",
        "note": "Read-only state probe; no vendor calls are issued. API key VALUES and base URLs are never returned.",
    }
