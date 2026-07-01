"""
Revenue Management Engine Router - Dynamic pricing, demand analysis, yield rules, channel strategy.
All endpoints under /api/revenue-engine/
"""

from datetime import UTC, datetime, timedelta
from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cache_manager import cached
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from modules.revenue_management.revenue_engine import RevenueManagementEngine

router = APIRouter(prefix="/api/revenue-engine", tags=["revenue-engine"])
engine = RevenueManagementEngine()


class ApplyRateRequest(BaseModel):
    target_date: str
    new_rate: float


# ── DEMAND ANALYSIS ──


@router.get("/booking-pace")
@cached(ttl=300, key_prefix="revenue_booking_pace")
async def api_booking_pace(
    target_date: str | None = None,
    lookback_days: int = 30,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v73 Bug DI: booking pace = revenue intel
):
    """Get booking pace analysis for a target date."""
    if not target_date:
        target_date = datetime.now(UTC).date().isoformat()
    return await engine.get_booking_pace(current_user.tenant_id, target_date, lookback_days)


@router.get("/pickup-trends")
async def api_pickup_trends(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get reservation pickup trends."""
    today = datetime.now(UTC).date()
    if not start_date:
        start_date = (today - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = today.isoformat()
    try:
        sd = date_cls.fromisoformat(start_date)
        ed = date_cls.fromisoformat(end_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")
    if (ed - sd).days > 30:
        raise HTTPException(status_code=400, detail="Max 30 day range")
    return await engine.get_pickup_trends(current_user.tenant_id, start_date, end_date)


@router.get("/occupancy-forecast")
@cached(ttl=600, key_prefix="rev_occ_forecast")  # 10dk cache (Tur 2 fix)
async def api_occupancy_forecast(days: int = 14, current_user: User = Depends(get_current_user)):
    """Get occupancy forecast."""
    if days > 60:
        raise HTTPException(status_code=400, detail="Max 60 days")
    return await engine.get_occupancy_forecast(current_user.tenant_id, days)


@router.get("/lead-time-analysis")
async def api_lead_time(days_back: int = 30, current_user: User = Depends(get_current_user)):
    """Get booking lead time analysis."""
    return await engine.get_lead_time_analysis(current_user.tenant_id, days_back)


# ── RATE OPTIMIZATION ──


@router.get("/ideal-adr")
async def api_ideal_adr(
    target_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Calculate ideal ADR for a target date."""
    if not target_date:
        target_date = datetime.now(UTC).date().isoformat()
    return await engine.calculate_ideal_adr(current_user.tenant_id, target_date)


@router.get("/rate-suggestions")
@cached(ttl=600, key_prefix="rev_rate_suggestions")  # 10dk cache (Tur 2 fix)
async def api_rate_suggestions(days: int = 7, current_user: User = Depends(get_current_user)):
    """Get rate suggestions for upcoming days."""
    if days > 30:
        raise HTTPException(status_code=400, detail="Max 30 days")
    return await engine.get_rate_suggestions(current_user.tenant_id, days)


# ── YIELD RULES ──


@router.get("/yield-recommendations")
@cached(ttl=600, key_prefix="rev_yield_rec")  # 10dk cache (Tur 2 fix)
async def api_yield_recommendations(current_user: User = Depends(get_current_user)):
    """Get yield management recommendations."""
    return await engine.get_yield_recommendations(current_user.tenant_id)


# ── CHANNEL STRATEGY ──


@router.get("/channel-performance")
async def api_channel_performance(days_back: int = 30, current_user: User = Depends(get_current_user)):
    """Get channel mix and performance analysis."""
    return await engine.get_channel_performance(current_user.tenant_id, days_back)


# ── DASHBOARD ──


@router.get("/dashboard")
@cached(ttl=300, key_prefix="rev_dashboard")  # 5dk cache (Tur 2 fix)
async def api_revenue_dashboard(current_user: User = Depends(get_current_user)):
    """Get comprehensive revenue management dashboard."""
    return await engine.get_revenue_dashboard(current_user.tenant_id)


# ── AUTOMATION ──


@router.post("/apply-rate")
async def api_apply_rate(
    req: ApplyRateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Apply a rate suggestion for a specific date."""
    return await engine.apply_rate_suggestion(current_user.tenant_id, req.target_date, req.new_rate, current_user.id)
