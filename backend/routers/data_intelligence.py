"""
Data Intelligence Router - Unified API for Revenue ML Pipeline, Operational AI, and Guest Intelligence.
Endpoint groups:
  /api/data-intelligence/revenue/*
  /api/data-intelligence/operations/*
  /api/data-intelligence/guests/*
"""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.data_intelligence.guest_intelligence import guest_intelligence
from modules.data_intelligence.operational_ai import operational_ai
from modules.data_intelligence.revenue_ml_pipeline import revenue_pipeline
from modules.pms_core.role_permission_service import require_op  # v73 Bug DI

try:
    from cache_manager import cache, cached
except ImportError:  # pragma: no cover
    cache = None

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


def _invalidate_forecast(tenant_id: str):
    """Sprint 33 R6: invalidate forecast_dashboard cache after pipeline run."""
    if cache is not None and tenant_id:
        try:
            cache.safe_invalidate(tenant_id, "forecast_dashboard")
        except Exception:  # pragma: no cover
            pass


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-intelligence", tags=["data-intelligence"])


# ═══════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════


class RunPipelineReq(BaseModel):
    room_type: str | None = None
    target_date: str | None = None
    property_id: str | None = None


# ═══════════════════════════════════════════════════════════
# 1. REVENUE INTELLIGENCE
# ═══════════════════════════════════════════════════════════


@router.post("/revenue/run-pipeline")
async def run_revenue_pipeline(
    req: RunPipelineReq,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Execute the full Revenue ML Pipeline."""
    result = await revenue_pipeline.run_pipeline(
        tenant_id=current_user.tenant_id,
        room_type=req.room_type,
        target_date=req.target_date,
        property_id=req.property_id,
    )
    _invalidate_forecast(current_user.tenant_id)
    return result


@router.get("/revenue/forecast-dashboard")
@cached(ttl=600, key_prefix="forecast_dashboard")  # heavy ML aggregate (10min cache)
async def get_revenue_forecast_dashboard(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v73 Bug DI: stratejik ML/forecast
):
    """Get comprehensive revenue forecast dashboard.
    Cached 120s — underlying ML models scan bookings/folio_charges (25s cold).
    Mutations on bookings/pricing recommendations should invalidate via
    `cache.safe_invalidate(tenant_id, 'forecast_dashboard')`.
    """
    return await revenue_pipeline.get_forecast_dashboard(current_user.tenant_id)


@router.get("/revenue/recommendations")
async def get_revenue_recommendations(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v75 Bug DK
):
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
async def get_operations_dashboard(target_date: str | None = None, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_executive_reports"))):
    """Get full operational AI dashboard."""
    return await operational_ai.get_dashboard(current_user.tenant_id, target_date)


@router.get("/operations/staffing")
async def get_staffing_recommendations(target_date: str | None = None, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_executive_reports"))):
    """Get staffing recommendations for front desk and housekeeping."""
    return await operational_ai.get_staffing_recommendations(current_user.tenant_id, target_date)


@router.get("/operations/workload-heatmap")
async def get_workload_heatmap(target_date: str | None = None, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_executive_reports"))):
    """Get housekeeping workload heatmap and check-in hourly distribution."""
    return await operational_ai.get_workload_heatmap(current_user.tenant_id, target_date)


@router.get("/operations/room-readiness")
async def get_room_readiness(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Get room readiness ETA predictions."""
    return await operational_ai.readiness.predict(current_user.tenant_id)


@router.get("/operations/maintenance-risk")
async def get_maintenance_risk(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Get maintenance failure risk predictions."""
    return await operational_ai.maintenance.predict(current_user.tenant_id)


# ═══════════════════════════════════════════════════════════
# 3. GUEST INTELLIGENCE
# ═══════════════════════════════════════════════════════════


@router.get("/guests/dashboard")
async def get_guest_dashboard(limit: int = Query(30, ge=1, le=100), current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_guest_list"))):
    """Get aggregate guest intelligence dashboard."""
    return await guest_intelligence.get_dashboard(current_user.tenant_id, limit)


@router.get("/guests/{guest_id}/summary")
async def get_guest_summary(guest_id: str, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_guest_list"))):
    """Get complete intelligence for a single guest."""
    return await guest_intelligence.get_guest_summary(current_user.tenant_id, guest_id)


@router.get("/guests/{guest_id}/churn-risk")
async def get_guest_churn_risk(guest_id: str, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_guest_list"))):
    """Get churn prediction for a guest."""
    return await guest_intelligence.churn.predict(current_user.tenant_id, guest_id)


@router.get("/guests/{guest_id}/upsell")
async def get_guest_upsell(guest_id: str, booking_id: str | None = None, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_guest_list"))):
    """Get upsell recommendations for a guest."""
    return await guest_intelligence.upsell.recommend(current_user.tenant_id, guest_id, booking_id)


@router.get("/guests/segments")
async def get_guest_segments(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_guest_list")),
):
    """Get guest segment distribution."""
    dash = await guest_intelligence.get_dashboard(current_user.tenant_id, 30)
    return {
        "segment_distribution": dash.get("segment_distribution", {}),
        "value_distribution": dash.get("value_distribution", {}),
    }


@router.get("/guests/churn-summary")
async def get_churn_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_guest_list")),
):
    """Get churn risk summary across all guests."""
    dash = await guest_intelligence.get_dashboard(current_user.tenant_id, 30)
    return {
        "churn_risk_summary": dash.get("churn_risk_summary", {}),
        "high_churn_guests": dash.get("high_churn_guests", []),
    }


@router.get("/guests/upsell-opportunities")
async def get_upsell_opportunities(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_guest_list")),
):
    """Get upsell opportunities across all guests."""
    dash = await guest_intelligence.get_dashboard(current_user.tenant_id, 30)
    return {
        "opportunities": dash.get("upsell_opportunities", []),
        "total_potential": sum(o.get("potential", 0) for o in dash.get("upsell_opportunities", [])),
    }


@router.get("/overview")
@cached(ttl=300, key_prefix="data_intelligence_overview")
async def get_data_intelligence_overview(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Aggregate overview combining revenue, operations, and guest intelligence KPIs.
    Used by DataIntelligenceDashboard summary widget and audit endpoints.
    """
    revenue_dash = await revenue_pipeline.get_forecast_dashboard(current_user.tenant_id)
    ops_dash = await operational_ai.get_dashboard(current_user.tenant_id, None)
    guest_dash = await guest_intelligence.get_dashboard(current_user.tenant_id, 10)
    return {
        "revenue": {
            "forecast_accuracy": revenue_dash.get("model_accuracy", 0),
            "recommendations_pending": len(revenue_dash.get("pricing_recommendations", [])),
            "adr_trend": revenue_dash.get("adr_trend", []),
        },
        "operations": {
            "room_readiness_score": ops_dash.get("room_readiness_score", 0),
            "staffing_status": ops_dash.get("staffing_status", "unknown"),
            "maintenance_alerts": ops_dash.get("maintenance_risk_count", 0),
        },
        "guests": {
            "total_analyzed": guest_dash.get("total_guests", 0),
            "high_churn_count": len(guest_dash.get("high_churn_guests", [])),
            "upsell_opportunities": len(guest_dash.get("upsell_opportunities", [])),
        },
        "status": "ok",
    }
