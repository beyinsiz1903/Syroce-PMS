"""
Channel Manager — Hardening Router
Production runtime APIs for drift detection, reconciliation,
sync scheduling, provider health, and credential management.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime, timezone

from core.database import db
from core.security import get_current_user
from core.helpers import require_admin
from models.schemas import User

from domains.channel_manager.drift_detector import drift_detector
from domains.channel_manager.reconciliation_engine import reconciliation_engine
from domains.channel_manager.sync_scheduler import sync_scheduler
from domains.channel_manager.provider_failover import provider_failover
from domains.channel_manager.runtime_status import cm_runtime_status
from domains.channel_manager.encryption import encrypt_credential, mask_credential

router = APIRouter(prefix="/api/channel-manager", tags=["Channel Manager / Hardening"])


# ── Runtime Status ──────────────────────────────────────────────────

@router.get("/runtime/status", summary="CM runtime health overview")
async def get_runtime_status(current_user: User = Depends(get_current_user)):
    """Aggregated health status across sync, drift, reconciliation, and providers."""
    return await cm_runtime_status.get_status(current_user.tenant_id)


# ── Drift Detection ────────────────────────────────────────────────

@router.post("/drift/scan", summary="Trigger drift scan")
async def trigger_drift_scan(current_user: User = Depends(get_current_user)):
    """Run an on-demand drift scan comparing PMS state with OTA snapshots."""
    result = await drift_detector.scan_drift(current_user.tenant_id)
    return result


@router.get("/drift/issues", summary="Get drift issues")
async def get_drift_issues(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get recent drift scan results and detected issues."""
    history = await drift_detector.get_drift_history(
        current_user.tenant_id, limit=limit
    )
    return {"tenant_id": current_user.tenant_id, "scans": history, "count": len(history)}


# ── Reconciliation ─────────────────────────────────────────────────

@router.post("/reconciliation/run", summary="Run reconciliation")
async def run_reconciliation(
    auto_fix: bool = Query(True),
    current_user: User = Depends(get_current_user),
):
    """Run reconciliation engine: detect drift and optionally auto-fix."""
    result = await reconciliation_engine.reconcile(
        current_user.tenant_id, auto_fix=auto_fix
    )
    return result


@router.get("/reconciliation/history", summary="Reconciliation history")
async def get_reconciliation_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get recent reconciliation results."""
    history = await reconciliation_engine.get_reconciliation_history(
        current_user.tenant_id, limit=limit
    )
    return {"tenant_id": current_user.tenant_id, "results": history, "count": len(history)}


# ── Sync Schedule ──────────────────────────────────────────────────

@router.get("/sync/schedule", summary="Get sync schedule status")
async def get_sync_schedule(current_user: User = Depends(get_current_user)):
    """Get current sync scheduler status and configuration."""
    return {
        "running": sync_scheduler._running,
        "interval_seconds": sync_scheduler._interval_seconds,
        "tenant_id": current_user.tenant_id,
    }


@router.post("/sync/trigger", summary="Trigger immediate sync")
async def trigger_sync(
    event_type: str = Query("manual", description="Event type triggering sync"),
    current_user: User = Depends(get_current_user),
):
    """Trigger an immediate sync for all active connections."""
    results = await sync_scheduler.trigger_event_sync(
        current_user.tenant_id, event_type, {"triggered_by": current_user.id}
    )
    return {"status": "triggered", "results": results}


# ── Provider Health ────────────────────────────────────────────────

@router.get("/providers/health", summary="Provider health status")
async def get_providers_health(current_user: User = Depends(get_current_user)):
    """Get health and circuit breaker status for all OTA providers."""
    provider_health = await cm_runtime_status.get_provider_health(current_user.tenant_id)
    return {
        "tenant_id": current_user.tenant_id,
        "providers": provider_health,
        "circuit_breakers": provider_failover.get_all_status(),
    }


@router.post("/providers/{provider}/reset", summary="Reset provider circuit breaker")
async def reset_provider_circuit(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Manually reset a provider's circuit breaker."""
    provider_failover.reset_breaker(provider)
    return {
        "status": "reset",
        "provider": provider,
        "circuit_state": provider_failover.get_breaker(provider).get_status(),
    }


# ── Credential Management ─────────────────────────────────────────

@router.post("/credentials/encrypt", summary="Encrypt provider credential")
async def encrypt_provider_credential(
    connection_id: str = Query(...),
    credential_key: str = Query(..., description="e.g. api_key, api_secret"),
    credential_value: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Encrypt and store a provider credential at rest."""
    encrypted = encrypt_credential(credential_value)
    await db.channel_connections.update_one(
        {"id": connection_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            f"encrypted_credentials.{credential_key}": encrypted,
            "credentials_encrypted": True,
            "credentials_updated_at": datetime.now(timezone.utc).isoformat(),
            "credentials_updated_by": current_user.id,
        }},
    )
    return {
        "status": "encrypted",
        "connection_id": connection_id,
        "credential_key": credential_key,
        "masked_value": mask_credential(credential_value),
    }
