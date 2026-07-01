"""
Incident Response & Recovery — API Router
==========================================
Incident lifecycle: create, ack, resolve, list.
Recovery tools: replay DLQ, recover stuck workers, force recon.
Service health matrix.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from common.context import OperationContext
from common.response import from_service_result
from core.security import get_current_user
from modules.incident.incident_service import incident_response_service
from modules.pms_core.role_permission_service import require_op  # v101 DW

router = APIRouter(prefix="/api/incidents", tags=["Incident Response"])


class CreateIncidentRequest(BaseModel):
    title: str
    description: str
    severity: str = "P2"
    affected_service: str = ""
    affected_tenant_id: str | None = None
    affected_property_id: str | None = None


class AckIncidentRequest(BaseModel):
    incident_id: str


class ResolveIncidentRequest(BaseModel):
    incident_id: str
    resolution_note: str


class ReplayDLQRequest(BaseModel):
    queue_name: str
    max_count: int = 10
    reason: str


class RecoverWorkersRequest(BaseModel):
    stale_minutes: int = 30


class ForceReconRequest(BaseModel):
    provider_id: str
    reason: str


@router.post("/create")
async def create_incident(
    req: CreateIncidentRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await incident_response_service.create_incident(ctx, req.title, req.description, req.severity, req.affected_service, req.affected_tenant_id, req.affected_property_id)
    return from_service_result(result)


@router.post("/acknowledge")
async def acknowledge_incident(
    req: AckIncidentRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await incident_response_service.acknowledge_incident(ctx, req.incident_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/resolve")
async def resolve_incident(
    req: ResolveIncidentRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await incident_response_service.resolve_incident(ctx, req.incident_id, req.resolution_note)
    if not result.ok:
        raise HTTPException(status_code=404, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/list")
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await incident_response_service.list_incidents(ctx, status, severity, limit)
    return from_service_result(result)


@router.post("/recovery/replay-dlq")
async def replay_dead_letters(
    req: ReplayDLQRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await incident_response_service.replay_dead_letters(ctx, req.queue_name, req.max_count, reason=req.reason)
    if not result.ok:
        code = 403 if result.code == "FORBIDDEN" else 400
        raise HTTPException(status_code=code, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/recovery/stuck-workers")
async def recover_stuck_workers(
    req: RecoverWorkersRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await incident_response_service.recover_stuck_workers(ctx, req.stale_minutes)
    if not result.ok:
        code = 403 if result.code == "FORBIDDEN" else 400
        raise HTTPException(status_code=code, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/recovery/force-reconciliation")
async def force_reconciliation(
    req: ForceReconRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await incident_response_service.force_reconciliation(ctx, req.provider_id, reason=req.reason)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/service-health")
async def service_health_matrix(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await incident_response_service.get_service_health_matrix(ctx)
    return from_service_result(result)
