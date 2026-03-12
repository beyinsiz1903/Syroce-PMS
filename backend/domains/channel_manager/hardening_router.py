"""
Channel Manager — Hardening Router
Production runtime APIs for drift detection, reconciliation,
sync scheduling, provider health, and credential management.
Thin router: delegates all business logic to CMRuntimeService.
"""
from fastapi import APIRouter, HTTPException, Depends, Query

from core.security import get_current_user
from models.schemas import User
from common.context import OperationContext
from domains.channel_manager.cm_runtime_service import cm_runtime_service

router = APIRouter(prefix="/api/channel-manager", tags=["Channel Manager / Hardening"])


def _ctx(user: User) -> OperationContext:
    return OperationContext.from_user(user)


@router.get("/runtime/status", summary="CM runtime health overview")
async def get_runtime_status(current_user: User = Depends(get_current_user)):
    result = await cm_runtime_service.get_runtime_status(_ctx(current_user))
    return result.data


@router.post("/drift/scan", summary="Trigger drift scan")
async def trigger_drift_scan(current_user: User = Depends(get_current_user)):
    result = await cm_runtime_service.trigger_drift_scan(_ctx(current_user))
    return result.data


@router.get("/drift/issues", summary="Get drift issues")
async def get_drift_issues(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    result = await cm_runtime_service.get_drift_issues(_ctx(current_user), limit=limit)
    return result.data


@router.post("/reconciliation/run", summary="Run reconciliation")
async def run_reconciliation(
    auto_fix: bool = Query(True),
    current_user: User = Depends(get_current_user),
):
    result = await cm_runtime_service.run_reconciliation(_ctx(current_user), auto_fix=auto_fix)
    return result.data


@router.get("/reconciliation/history", summary="Reconciliation history")
async def get_reconciliation_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    result = await cm_runtime_service.get_reconciliation_history(_ctx(current_user), limit=limit)
    return result.data


@router.get("/sync/schedule", summary="Get sync schedule status")
async def get_sync_schedule(current_user: User = Depends(get_current_user)):
    result = await cm_runtime_service.get_sync_schedule(_ctx(current_user))
    return result.data


@router.post("/sync/trigger", summary="Trigger immediate sync")
async def trigger_sync(
    event_type: str = Query("manual", description="Event type triggering sync"),
    current_user: User = Depends(get_current_user),
):
    result = await cm_runtime_service.trigger_sync(_ctx(current_user), event_type=event_type)
    return result.data


@router.get("/providers/health", summary="Provider health status")
async def get_providers_health(current_user: User = Depends(get_current_user)):
    result = await cm_runtime_service.get_providers_health(_ctx(current_user))
    return result.data


@router.post("/providers/{provider}/reset", summary="Reset provider circuit breaker")
async def reset_provider_circuit(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    result = await cm_runtime_service.reset_provider_circuit(_ctx(current_user), provider)
    return result.data


@router.post("/credentials/encrypt", summary="Encrypt provider credential")
async def encrypt_provider_credential(
    connection_id: str = Query(...),
    credential_key: str = Query(..., description="e.g. api_key, api_secret"),
    credential_value: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    result = await cm_runtime_service.encrypt_credential(
        _ctx(current_user), connection_id, credential_key, credential_value
    )
    return result.data
