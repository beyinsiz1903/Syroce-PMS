"""Alerting system and reliability monitoring endpoints."""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v100 DW

from ...application.alerting_service import AlertingService
from ...application.multi_property_service import MultiPropertyService
from ...application.reliability_service import ReliabilityService

logger = logging.getLogger("channel_manager.routers.alert")

router = APIRouter(tags=["CM Alerts & Reliability"])


class AlertRuleRequest(BaseModel):
    trigger: str
    threshold: float = 1
    severity: str = "warning"
    description: str = ""
    enabled: bool = True
    connector_id: str | None = None


class AlertActionRequest(BaseModel):
    reason: str = ""
    hours: int = 24


# ─── Alerts ───────────────────────────────────────────────────────


@router.get("/alerts")
async def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    connector_id: str | None = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = AlertingService()
    alerts = await svc.get_alerts(current_user.tenant_id, status, severity, connector_id, limit)
    summary = await svc.get_alert_summary(current_user.tenant_id)
    return {"alerts": alerts, "count": len(alerts), "summary": summary}


@router.get("/alerts/summary")
async def get_alert_summary(
    current_user: User = Depends(get_current_user),
):
    svc = AlertingService()
    return await svc.get_alert_summary(current_user.tenant_id)


@router.post("/alerts/evaluate")
async def evaluate_alerts(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = AlertingService()
    return await svc.evaluate_alerts(current_user.tenant_id)


@router.get("/alerts/rules")
async def list_alert_rules(
    current_user: User = Depends(get_current_user),
):
    svc = AlertingService()
    rules = await svc.get_rules(current_user.tenant_id)
    return {"rules": rules, "count": len(rules)}


@router.post("/alerts/rules")
async def create_alert_rule(
    req: AlertRuleRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = AlertingService()
    rule = await svc.create_rule(current_user.tenant_id, req.model_dump(), current_user.id)
    return {"message": "Rule created", "rule": rule}


@router.put("/alerts/rules/{rule_id}")
async def update_alert_rule(
    rule_id: str,
    req: AlertRuleRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = AlertingService()
    rule = await svc.update_rule(current_user.tenant_id, rule_id, req.model_dump(), current_user.id)
    return {"message": "Rule updated", "rule": rule}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = AlertingService()
    deleted = await svc.delete_rule(current_user.tenant_id, rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted"}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = AlertingService()
    return await svc.acknowledge_alert(current_user.tenant_id, alert_id, current_user.id)


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    req: AlertActionRequest = Body(AlertActionRequest()),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = AlertingService()
    return await svc.resolve_alert(current_user.tenant_id, alert_id, current_user.id, req.reason)


@router.post("/alerts/{alert_id}/mute")
async def mute_alert(
    alert_id: str,
    req: AlertActionRequest = Body(AlertActionRequest()),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = AlertingService()
    return await svc.mute_alert(current_user.tenant_id, alert_id, req.hours, current_user.id)


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    req: AlertActionRequest = Body(AlertActionRequest()),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    svc = AlertingService()
    return await svc.dismiss_alert(current_user.tenant_id, alert_id, current_user.id, req.reason)


# ─── Reliability ──────────────────────────────────────────────────


@router.get("/reliability")
async def get_all_reliability(
    current_user: User = Depends(get_current_user),
):
    svc = ReliabilityService()
    return await svc.get_all_reliability(current_user.tenant_id)


@router.get("/reliability/{connector_id}")
async def get_connector_reliability(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReliabilityService()
    result = await svc.get_reliability(current_user.tenant_id, connector_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/reliability/property/{property_id}")
async def get_property_reliability(
    property_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReliabilityService()
    result = await svc.get_reliability_by_property(current_user.tenant_id, property_id)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── Multi-Property Dashboard ────────────────────────────────────


@router.get("/multi-property/dashboard")
async def get_multi_property_dashboard(
    current_user: User = Depends(get_current_user),
):
    svc = MultiPropertyService()
    return await svc.get_dashboard(current_user.tenant_id)


@router.get("/multi-property/comparison")
async def get_multi_property_comparison(
    current_user: User = Depends(get_current_user),
):
    svc = MultiPropertyService()
    return await svc.get_comparison(current_user.tenant_id)


@router.get("/multi-property/issues")
async def get_multi_property_issues(
    current_user: User = Depends(get_current_user),
):
    svc = MultiPropertyService()
    return await svc.get_issues(current_user.tenant_id)


@router.get("/multi-property/health")
async def get_multi_property_health(
    current_user: User = Depends(get_current_user),
):
    svc = MultiPropertyService()
    return await svc.get_health(current_user.tenant_id)
