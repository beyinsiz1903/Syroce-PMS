"""
Data Intelligence Router - Unified API for Revenue ML Pipeline, Operational AI, and Guest Intelligence.
Endpoint groups:
  /api/data-intelligence/revenue/*
  /api/data-intelligence/operations/*
  /api/data-intelligence/guests/*
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.data_intelligence.guest_intelligence import guest_intelligence
from modules.data_intelligence.operational_ai import operational_ai
from modules.data_intelligence.revenue_ml_pipeline import revenue_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-intelligence", tags=["data-intelligence"])


# ═══════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════

class RunPipelineReq(BaseModel):
    room_type: Optional[str] = None
    target_date: Optional[str] = None
    property_id: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# 1. REVENUE INTELLIGENCE
# ═══════════════════════════════════════════════════════════

@router.post("/revenue/run-pipeline")
async def run_revenue_pipeline(req: RunPipelineReq,
                                current_user: User = Depends(get_current_user)):
    """Execute the full Revenue ML Pipeline."""
    return await revenue_pipeline.run_pipeline(
        tenant_id=current_user.tenant_id,
        room_type=req.room_type,
        target_date=req.target_date,
        property_id=req.property_id,
    )


@router.get("/revenue/forecast-dashboard")
async def get_revenue_forecast_dashboard(current_user: User = Depends(get_current_user)):
    """Get comprehensive revenue forecast dashboard."""
    return await revenue_pipeline.get_forecast_dashboard(current_user.tenant_id)


@router.get("/revenue/recommendations")
async def get_revenue_recommendations(current_user: User = Depends(get_current_user)):
    """Get recent ML pricing recommendations."""
    from modules.platform_scaling.revenue_autopricing import autopricing
    pending = await autopricing.get_pending_recommendations(current_user.tenant_id)
    history = await autopricing.get_recommendation_history(current_user.tenant_id, 20)
    return {
        "pending": pending,
        "history": history,
    }


# ═══════════════════════════════════════════════════════════
# 2. OPERATIONAL AI
# ═══════════════════════════════════════════════════════════

@router.get("/operations/dashboard")
async def get_operations_dashboard(target_date: Optional[str] = None,
                                    current_user: User = Depends(get_current_user)):
    """Get full operational AI dashboard."""
    return await operational_ai.get_dashboard(current_user.tenant_id, target_date)


@router.get("/operations/staffing")
async def get_staffing_recommendations(target_date: Optional[str] = None,
                                        current_user: User = Depends(get_current_user)):
    """Get staffing recommendations for front desk and housekeeping."""
    return await operational_ai.get_staffing_recommendations(current_user.tenant_id, target_date)


@router.get("/operations/workload-heatmap")
async def get_workload_heatmap(target_date: Optional[str] = None,
                                current_user: User = Depends(get_current_user)):
    """Get housekeeping workload heatmap and check-in hourly distribution."""
    return await operational_ai.get_workload_heatmap(current_user.tenant_id, target_date)


@router.get("/operations/room-readiness")
async def get_room_readiness(current_user: User = Depends(get_current_user)):
    """Get room readiness ETA predictions."""
    return await operational_ai.readiness.predict(current_user.tenant_id)


@router.get("/operations/maintenance-risk")
async def get_maintenance_risk(current_user: User = Depends(get_current_user)):
    """Get maintenance failure risk predictions."""
    return await operational_ai.maintenance.predict(current_user.tenant_id)


# ═══════════════════════════════════════════════════════════
# 3. GUEST INTELLIGENCE
# ═══════════════════════════════════════════════════════════

@router.get("/guests/dashboard")
async def get_guest_dashboard(limit: int = Query(30, ge=1, le=100),
                               current_user: User = Depends(get_current_user)):
    """Get aggregate guest intelligence dashboard."""
    return await guest_intelligence.get_dashboard(current_user.tenant_id, limit)


@router.get("/guests/{guest_id}/summary")
async def get_guest_summary(guest_id: str,
                             current_user: User = Depends(get_current_user)):
    """Get complete intelligence for a single guest."""
    return await guest_intelligence.get_guest_summary(current_user.tenant_id, guest_id)


@router.get("/guests/{guest_id}/churn-risk")
async def get_guest_churn_risk(guest_id: str,
                                current_user: User = Depends(get_current_user)):
    """Get churn prediction for a guest."""
    return await guest_intelligence.churn.predict(current_user.tenant_id, guest_id)


@router.get("/guests/{guest_id}/upsell")
async def get_guest_upsell(guest_id: str, booking_id: Optional[str] = None,
                            current_user: User = Depends(get_current_user)):
    """Get upsell recommendations for a guest."""
    return await guest_intelligence.upsell.recommend(
        current_user.tenant_id, guest_id, booking_id
    )


@router.get("/guests/segments")
async def get_guest_segments(current_user: User = Depends(get_current_user)):
    """Get guest segment distribution."""
    dash = await guest_intelligence.get_dashboard(current_user.tenant_id, 30)
    return {
        "segment_distribution": dash.get("segment_distribution", {}),
        "value_distribution": dash.get("value_distribution", {}),
    }


@router.get("/guests/churn-summary")
async def get_churn_summary(current_user: User = Depends(get_current_user)):
    """Get churn risk summary across all guests."""
    dash = await guest_intelligence.get_dashboard(current_user.tenant_id, 30)
    return {
        "churn_risk_summary": dash.get("churn_risk_summary", {}),
        "high_churn_guests": dash.get("high_churn_guests", []),
    }


@router.get("/guests/upsell-opportunities")
async def get_upsell_opportunities(current_user: User = Depends(get_current_user)):
    """Get upsell opportunities across all guests."""
    dash = await guest_intelligence.get_dashboard(current_user.tenant_id, 30)
    return {
        "opportunities": dash.get("upsell_opportunities", []),
        "total_potential": sum(o.get("potential", 0) for o in dash.get("upsell_opportunities", [])),
    }
