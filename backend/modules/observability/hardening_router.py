"""
Observability — Hardening Router
Unified runtime metrics and alert endpoints.
"""

from fastapi import APIRouter, Depends

from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/observability", tags=["Observability / Runtime"])


@router.get("/runtime/metrics", summary="Runtime metrics snapshot")
async def get_runtime_metrics(current_user: User = Depends(get_current_user)):
    """Collect all runtime hardening metrics for the tenant."""
    from modules.observability.runtime_metrics import runtime_metrics

    return await runtime_metrics.collect_all(current_user.tenant_id)


@router.get("/runtime/alerts", summary="Active runtime alerts")
async def get_runtime_alerts(current_user: User = Depends(get_current_user)):
    """Get active alerts based on runtime metric thresholds."""
    from modules.observability.runtime_metrics import runtime_metrics

    alerts = await runtime_metrics.get_alerts(current_user.tenant_id)
    return {
        "tenant_id": current_user.tenant_id,
        "alerts": alerts,
        "count": len(alerts),
        "critical": sum(1 for a in alerts if a.get("severity") == "critical"),
    }
