"""
predictions

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


# ── GET /predictions/no-shows ──
@router.get("/predictions/no-shows")
async def predict_no_shows(
    target_date: str = None,
    current_user: User = Depends(get_current_user),
):
    """No-show risk predictions — tenant-scoped.

    F8O Task #214 (P0): previously returned hardcoded mock entries
    (`BK001`/`BK002`) for every caller, which collapsed the tenant boundary —
    any tenant's token surfaced the same fabricated booking IDs, tripping
    cross-tenant leak detectors and (more importantly) violating the
    threat-model "tenant boundary" invariant.

    Now scopes the lookup to `current_user.tenant_id` and only returns
    booking IDs that belong to that tenant. Empty result is the correct
    answer when there are no arrivals — never fall back to mock data.
    """
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")

    tenant_id = current_user.tenant_id
    bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "check_in": target_date,
            "status": {"$in": ["confirmed", "guaranteed"]},
        },
        {"_id": 0, "id": 1, "tenant_id": 1, "ota_channel": 1, "payment_model": 1, "total_amount": 1, "check_in": 1},
    ).to_list(1000)

    predictions = []
    for booking in bookings:
        # Defence-in-depth: skip any doc whose tenant_id does not match the
        # requesting user. The Mongo filter already guarantees this, but if
        # a future shared cache or query helper drops the filter, this
        # post-filter prevents an ID leak in the response.
        if booking.get("tenant_id") != tenant_id:
            continue

        # Risk weights (0..1 fractional scale to preserve the pre-fix GET
        # contract — frontend PredictiveAnalytics.jsx renders
        # `Math.round(pred.risk_score * 100)`, so this MUST stay in [0,1]).
        raw = 0.0
        if booking.get("ota_channel"):
            raw += 0.25
        payment_model = booking.get("payment_model")
        if payment_model == "agency":
            raw += 0.20
        elif payment_model == "hotel_collect":
            raw += 0.15
        if booking.get("total_amount", 0) < 100:
            raw += 0.10
        risk_score = round(min(1.0, max(0.0, raw)), 2)
        if risk_score >= 0.70:
            risk_level = "high"
        elif risk_score >= 0.50:
            risk_level = "medium"
        else:
            risk_level = "low"

        predictions.append(
            {
                "booking_id": booking.get("id"),
                "risk_score": risk_score,
                "risk_level": risk_level,
            }
        )

    return {
        "target_date": target_date,
        "predictions": predictions,
        "high_risk_count": sum(1 for p in predictions if p["risk_level"] == "high"),
        "total_at_risk": len(predictions),
    }


# ── GET /predictions/demand-forecast ──
@router.get("/predictions/demand-forecast")
async def demand_forecast(days: int = 30, current_user: User = Depends(get_current_user)):
    """30 günlük talep tahmini"""
    from domains.ai.predictive_engine import get_predictive_engine

    engine = get_predictive_engine(db)
    forecast = await engine.predict_demand(current_user.tenant_id, days)

    return {
        "forecast_period": f"{days} days",
        "daily_forecast": forecast,
        "avg_occupancy": round(sum([f["occupancy_forecast"] for f in forecast]) / len(forecast), 1) if forecast else 0,
        "peak_days": [f for f in forecast if f["demand_level"] == "very_high"],
    }


# ── GET /predictions/complaint-risk/{guest_id} ──
@router.get("/predictions/complaint-risk/{guest_id}")
async def predict_complaint_risk(guest_id: str, current_user: User = Depends(get_current_user)):
    """Misafir şikayet riski — gerçek geri bildirim geçmişinden hesaplanır.

    Sabit (0.35) skor kaldırıldı. Sinyal: misafirin geçmiş olumsuz departman
    geri bildirimleri (rating < 3). Geçmiş yoksa risk düşük + data_available:false.
    """
    guest = await db.guests.find_one({"id": guest_id, "tenant_id": current_user.tenant_id})
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    total_reviews = 0
    negative_reviews = 0
    async for r in db.department_feedback.find(
        {
            "guest_id": guest_id,
            "tenant_id": current_user.tenant_id,
        }
    ):
        total_reviews += 1
        if r.get("rating", 5) < 3:
            negative_reviews += 1

    factors = []
    raw = 0.0
    if negative_reviews > 0:
        raw += min(0.6, negative_reviews * 0.2)
        factors.append(f"{negative_reviews} olumsuz geri bildirim")
    if total_reviews >= 3 and (negative_reviews / total_reviews) >= 0.5:
        raw += 0.2
        factors.append("Olumsuz geri bildirim oranı yüksek")

    risk_score = round(min(1.0, max(0.0, raw)), 2)
    if risk_score >= 0.70:
        risk_level = "high"
    elif risk_score >= 0.40:
        risk_level = "medium"
    else:
        risk_level = "low"

    recommendation = "Proaktif hizmet kurtarma önerilir" if risk_level != "low" else "Standart hizmet yeterli"

    return {
        "guest_id": guest_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "factors": factors,
        "reviews_analyzed": total_reviews,
        "recommendation": recommendation,
        "data_available": total_reviews > 0,
    }


# ── POST /ai/predict-no-shows ──
@router.post("/ai/predict-no-shows")
async def predict_no_shows_detailed(
    date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """AI prediction of high-risk no-show bookings"""
    target_date = datetime.fromisoformat(date).date()

    # Get arrivals for target date
    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": target_date.isoformat(), "status": {"$in": ["confirmed", "guaranteed"]}}, {"_id": 0}).to_list(1000)

    predictions = []

    for booking in bookings:
        risk_score = 0
        risk_factors = []

        # Factor 1: Channel risk (OTA bookings higher risk)
        if booking.get("ota_channel"):
            risk_score += 25
            risk_factors.append(f"OTA booking ({booking.get('ota_channel')})")
        else:
            risk_score += 5

        # Factor 2: Payment method
        payment_model = booking.get("payment_model")
        if payment_model == "agency":
            risk_score += 20
            risk_factors.append("Agency payment (no prepayment)")
        elif payment_model == "hotel_collect":
            risk_score += 15
            risk_factors.append("Hotel collect (no prepayment)")
        elif payment_model == "virtual_card":
            risk_score += 5
            risk_factors.append("Virtual card")

        # Factor 3: Booking lead time (last-minute bookings higher risk)
        created_at = datetime.fromisoformat(booking.get("created_at", datetime.now(UTC).isoformat()))
        lead_time = (target_date - created_at.date()).days
        if lead_time < 2:
            risk_score += 20
            risk_factors.append(f"Last-minute booking ({lead_time} days)")
        elif lead_time < 7:
            risk_score += 10
            risk_factors.append(f"Short lead time ({lead_time} days)")

        # Factor 4: Guest history (if available)
        guest = await db.guests.find_one({"id": booking["guest_id"], "tenant_id": current_user.tenant_id}, {"_id": 0})
        if guest:
            past_bookings = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "guest_id": booking["guest_id"], "status": "checked_in"})

            if past_bookings == 0:
                risk_score += 15
                risk_factors.append("First-time guest")
            elif past_bookings > 3:
                risk_score -= 10
                risk_factors.append(f"Repeat guest ({past_bookings} stays)")

        # Factor 5: Booking amount (lower rates = higher risk)
        if booking.get("total_amount", 0) < 100:
            risk_score += 10
            risk_factors.append("Low booking value")

        # Normalize risk score (0-100)
        risk_score = min(100, max(0, risk_score))

        # Classify risk level
        if risk_score >= 70:
            risk_level = "high"
            recommendation = "Contact guest to confirm + Consider overbook strategy"
        elif risk_score >= 50:
            risk_level = "medium"
            recommendation = "Send reminder SMS/email 24h before arrival"
        else:
            risk_level = "low"
            recommendation = "Standard arrival preparation"

        predictions.append(
            {
                "booking_id": booking["id"],
                "guest_name": booking.get("guest_name", "Unknown"),
                "room_number": booking.get("room_number", "TBD"),
                "check_in": booking["check_in"],
                "risk_score": risk_score,
                "risk_level": risk_level,
                "risk_factors": risk_factors,
                "confidence": 0.75,
                "recommendation": recommendation,
                "channel": booking.get("ota_channel") or "direct",
                "booking_value": booking.get("total_amount", 0),
            }
        )

    # Sort by risk score descending
    predictions.sort(key=lambda x: x["risk_score"], reverse=True)

    return {
        "date": target_date.isoformat(),
        "total_arrivals": len(bookings),
        "predictions": predictions,
        "summary": {
            "high_risk_count": sum(1 for p in predictions if p["risk_level"] == "high"),
            "medium_risk_count": sum(1 for p in predictions if p["risk_level"] == "medium"),
            "low_risk_count": sum(1 for p in predictions if p["risk_level"] == "low"),
            "avg_risk_score": round(sum(p["risk_score"] for p in predictions) / len(predictions), 1) if predictions else 0,
        },
    }


# ── GET /ai/pms/occupancy-prediction ──
@router.get("/ai/pms/occupancy-prediction")
@cached(ttl=900, key_prefix="ai_occupancy_pred")
async def get_occupancy_prediction(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v86 DV: AI occupancy forecast
):
    """Get AI-powered occupancy prediction for next N days"""

    # Perf: rooms count + bookings find sıralı çalışıyordu (~2 RTT). Paralelize.
    import asyncio

    start_date = datetime.now(UTC)
    window_end = start_date + timedelta(days=days)
    
    start_date_iso = start_date.isoformat()
    window_end_iso = window_end.isoformat()

    total_rooms, booking_docs = await asyncio.gather(
        db.rooms.count_documents({"tenant_id": current_user.tenant_id}),
        db.bookings.find(
            {
                "tenant_id": current_user.tenant_id,
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
                "check_in": {"$lte": window_end_iso},
                "check_out": {"$gt": start_date_iso},
            },
            {"_id": 0, "check_in": 1, "check_out": 1},
        ).to_list(10000),
    )

    parsed_bookings = []
    for b in booking_docs:
        ci_raw, co_raw = b.get("check_in"), b.get("check_out")
        try:
            ci = ci_raw if isinstance(ci_raw, datetime) else datetime.fromisoformat(str(ci_raw).replace("Z", "+00:00"))
            co = co_raw if isinstance(co_raw, datetime) else datetime.fromisoformat(str(co_raw).replace("Z", "+00:00"))
            parsed_bookings.append((ci, co))
        except (ValueError, TypeError):
            continue

    predictions = []
    daily_occ = []
    for day_offset in range(days):
        pred_date = start_date + timedelta(days=day_offset)
        bookings_count = sum(1 for ci, co in parsed_bookings if ci <= pred_date < co)
        occupancy_pct = round((bookings_count / total_rooms * 100) if total_rooms > 0 else 0, 1)
        daily_occ.append(occupancy_pct)

        # Tahmin = gerçek on-the-books doluluk. Gelecek tarihler için onaylı
        # rezervasyonlar dolulugun TABANIDIR; uydurma hafta-ici/sonu carpani
        # (eski Cuma/Cmt x1.15, Pzt/Paz x0.85) KALDIRILDI — sahte varyans yok.
        predictions.append(
            {
                "date": pred_date.strftime("%Y-%m-%d"),
                "day_of_week": pred_date.strftime("%A"),
                "current_bookings": bookings_count,
                "current_occupancy_pct": occupancy_pct,
                "predicted_occupancy_pct": occupancy_pct,
                "confidence": "high" if day_offset < 7 else "medium" if day_offset < 14 else "low",
            }
        )

    # FrontdeskTab'in okudugu ust-duzey alanlar — hepsi gercek OTB verisinden.
    today_midnight = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    upcoming_bookings = sum(1 for ci, _co in parsed_bookings if ci >= today_midnight)
    current_occupancy = daily_occ[0] if daily_occ else 0
    tomorrow_prediction = daily_occ[1] if len(daily_occ) > 1 else current_occupancy
    next_week_slice = daily_occ[1:8] if len(daily_occ) > 1 else daily_occ[:1]
    next_week_prediction = round(sum(next_week_slice) / len(next_week_slice), 1) if next_week_slice else 0

    return {
        "predictions": predictions,
        "total_rooms": total_rooms,
        "prediction_period_days": days,
        "current_occupancy": current_occupancy,
        "upcoming_bookings": upcoming_bookings,
        "prediction": {
            "tomorrow_prediction": tomorrow_prediction,
            "next_week_prediction": next_week_prediction,
        },
    }


# ── GET /ai/pms/guest-patterns ──
@router.get("/ai/pms/guest-patterns")
@cached(ttl=900, key_prefix="ai_guest_patterns")
async def get_guest_patterns(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v86 DV: AI guest patterns analytics
):
    """AI-powered guest behavior pattern analysis"""

    from datetime import datetime, timedelta

    # Get recent bookings (last 90 days)
    ninety_days_ago = datetime.now() - timedelta(days=90)

    # Perf: projection eklendi — 5000 doc tam payload yerine yalnız ihtiyaç alanları.
    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "check_in": {"$gte": ninety_days_ago.isoformat()}},
        {
            "_id": 0,
            "check_in": 1,
            "check_out": 1,
            "created_at": 1,
            "room_id": 1,
            "booking_channel": 1,
            "status": 1,
        },
    ).to_list(length=5000)

    # Pre-fetch all referenced rooms in one batch (was N+1 inside loop)
    room_ids_in_bookings = list({b.get("room_id") for b in bookings if b.get("room_id")})
    room_type_map = {}
    if room_ids_in_bookings:
        async for r in db.rooms.find({"id": {"$in": room_ids_in_bookings}, "tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1, "room_type": 1}):
            room_type_map[r["id"]] = r.get("room_type", "standard")

    # Analyze patterns
    patterns = {"booking_lead_time": {}, "stay_duration": {}, "preferred_room_types": {}, "booking_channels": {}, "peak_seasons": {}, "cancellation_rate": 0}

    total_bookings = len(bookings)
    cancelled = 0
    lead_times = []
    durations = []
    room_types = {}
    channels = {}
    monthly_bookings = {}

    for booking in bookings:
        # Lead time
        if booking.get("created_at"):
            created = datetime.fromisoformat(booking["created_at"].replace("Z", "+00:00"))
            check_in = datetime.fromisoformat(booking["check_in"].replace("Z", "+00:00"))
            lead_time = (check_in - created).days
            lead_times.append(lead_time)

        # Duration
        check_in = datetime.fromisoformat(booking["check_in"].replace("Z", "+00:00"))
        check_out = datetime.fromisoformat(booking["check_out"].replace("Z", "+00:00"))
        duration = (check_out - check_in).days
        durations.append(duration)

        # Room type (lookup from pre-fetched batch)
        room_type = room_type_map.get(booking.get("room_id"))
        if room_type:
            room_types[room_type] = room_types.get(room_type, 0) + 1

        # Channel
        channel = booking.get("booking_channel", "direct")
        channels[channel] = channels.get(channel, 0) + 1

        # Month
        month = check_in.strftime("%B")
        monthly_bookings[month] = monthly_bookings.get(month, 0) + 1

        # Cancellation
        if booking.get("status") == "cancelled":
            cancelled += 1

    # Calculate averages and patterns
    patterns["booking_lead_time"] = {
        "average_days": round(sum(lead_times) / len(lead_times), 1) if lead_times else 0,
        "distribution": {
            "same_day": len([x for x in lead_times if x == 0]),
            "1-7_days": len([x for x in lead_times if 1 <= x <= 7]),
            "8-30_days": len([x for x in lead_times if 8 <= x <= 30]),
            "30+_days": len([x for x in lead_times if x > 30]),
        },
    }

    patterns["stay_duration"] = {
        "average_nights": round(sum(durations) / len(durations), 1) if durations else 0,
        "distribution": {
            "1_night": len([x for x in durations if x == 1]),
            "2-3_nights": len([x for x in durations if 2 <= x <= 3]),
            "4-7_nights": len([x for x in durations if 4 <= x <= 7]),
            "7+_nights": len([x for x in durations if x > 7]),
        },
    }

    patterns["preferred_room_types"] = room_types
    patterns["booking_channels"] = channels
    patterns["peak_seasons"] = monthly_bookings
    patterns["cancellation_rate"] = round((cancelled / total_bookings * 100), 2) if total_bookings > 0 else 0

    # AI Insights
    insights = []

    avg_lead = patterns["booking_lead_time"]["average_days"]
    if avg_lead < 7:
        insights.append("Misafirleriniz çoğunlukla son dakika rezervasyonu yapıyor. Esnek iptal politikası düşünün.")
    elif avg_lead > 30:
        insights.append("Misafirleriniz önceden planlama yapıyor. Erken rezervasyon indirimleri sunun.")

    if patterns["cancellation_rate"] > 15:
        insights.append(f"İptal oranı yüksek (%{patterns['cancellation_rate']}). İptal koşullarını gözden geçirin.")

    avg_stay = patterns["stay_duration"]["average_nights"]
    if avg_stay < 2:
        insights.append("Kısa süreli konaklamalar yaygın. Transit misafir profili olabilir.")
    elif avg_stay > 5:
        insights.append("Uzun süreli konaklamalar yaygın. Haftalık paket fiyatları sunun.")

    return {"success": True, "total_bookings_analyzed": total_bookings, "patterns": patterns, "ai_insights": insights, "generated_at": datetime.now().isoformat()}
