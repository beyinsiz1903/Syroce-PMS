"""
Observability — Alert Enrichment API Router
============================================
Alert management: evaluate rules, list active, acknowledge, resolve, get summary.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from common.context import OperationContext
from common.response import from_service_result
from core.security import get_current_user
from modules.observability.alert_enrichment import alert_enrichment_engine

router = APIRouter(prefix="/api/alerts", tags=["Alert Enrichment"])


class EvaluateRequest(BaseModel):
    metrics: dict

class AcknowledgeRequest(BaseModel):
    alert_id: str

class ResolveRequest(BaseModel):
    alert_id: str
    resolution_note: str = ""


@router.post("/evaluate")
async def evaluate_alerts(req: EvaluateRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await alert_enrichment_engine.evaluate_all_rules(ctx, req.metrics)
    return from_service_result(result)


@router.get("/active")
async def get_active_alerts(
    severity: str | None = None,
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await alert_enrichment_engine.get_active_alerts(ctx, severity, limit)
    return from_service_result(result)


@router.post("/acknowledge")
async def acknowledge_alert(req: AcknowledgeRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await alert_enrichment_engine.acknowledge_alert(ctx, req.alert_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/resolve")
async def resolve_alert(req: ResolveRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await alert_enrichment_engine.resolve_alert(ctx, req.alert_id, req.resolution_note)
    if not result.ok:
        raise HTTPException(status_code=404, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/summary")
async def get_alert_summary(
    hours: int = Query(24, ge=1, le=720),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await alert_enrichment_engine.get_alert_summary(ctx, hours)
    return from_service_result(result)


@router.get("/rules")
async def get_alert_rules(user=Depends(get_current_user)):
    rules = alert_enrichment_engine.get_rules()
    return {"status": "ok", "data": rules, "count": len(rules)}
