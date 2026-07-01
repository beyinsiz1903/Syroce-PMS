"""
Encryption Management Router — Comprehensive key lifecycle operations.

Provides API endpoints for:
  - Key registry (register, list, query)
  - Key state management (initiate rotation, complete, cancel, revoke)
  - Re-encryption jobs (create, start, pause, cancel, status)
  - Dashboard views (keys, jobs, audit)
  - Access control enforcement

All endpoints require admin or super_admin role.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from security.key_registry import KeyState, KeyType, get_key_registry
from security.reencryption_worker import JobState, get_reencryption_worker

logger = logging.getLogger("security.encryption_management_router")

router = APIRouter(
    prefix="/api/ops/encryption",
    tags=["Encryption Management"],
)


# ── Access Control ─────────────────────────────────────────────────


def _require_encryption_admin(user: User = Depends(get_current_user)) -> User:
    """Only super_admin or admin can manage encryption keys."""
    from core.security import _is_super_admin

    if _is_super_admin(user):
        return user
    if user.role not in ("super_admin", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Yetkisiz: Sifreleme yonetimi icin super_admin veya admin rolu gerekli",
        )
    return user


# ── Request Models ─────────────────────────────────────────────────


class RegisterKeyRequest(BaseModel):
    key_id: str
    key_type: str  # master, connector, webhook, api, pii
    description: str = ""
    tenant_id: str = ""
    provider: str = ""
    metadata: dict | None = None
    rotation_policy_days: int = 90


class InitiateRotationRequest(BaseModel):
    key_id: str
    reason: str = "scheduled"


class CompleteRotationRequest(BaseModel):
    key_id: str
    new_version: int | None = None


class CancelRotationRequest(BaseModel):
    key_id: str
    reason: str = "manual_cancel"


class EmergencyRevokeRequest(BaseModel):
    key_id: str
    reason: str
    notify_channels: list[str] | None = None


class CreateReencryptionJobRequest(BaseModel):
    key_id: str
    collections: list[str]
    batch_size: int = 100
    description: str = ""


class JobActionRequest(BaseModel):
    job_id: str
    reason: str = ""


# ── Key Registry Endpoints ─────────────────────────────────────────


@router.post("/keys/register")
async def register_key(
    body: RegisterKeyRequest,
    user: User = Depends(_require_encryption_admin),
):
    """Register a new encryption key in the registry.

    This tracks key metadata and lifecycle — the actual key material
    is managed separately via environment variables or KMS.
    """
    try:
        key_type = KeyType(body.key_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Gecersiz key_type: {body.key_type}. Gecerli degerler: {[t.value for t in KeyType]}",
        )

    registry = get_key_registry()
    result = await registry.register_key(
        key_id=body.key_id,
        key_type=key_type,
        description=body.description,
        tenant_id=body.tenant_id,
        provider=body.provider,
        metadata=body.metadata,
        rotation_policy_days=body.rotation_policy_days,
        actor=user.email,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Kayıt başarısız"))

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.get("/keys")
async def list_keys(
    state: str | None = Query(None, description="Filter by state: active, pending_rotation, retired, revoked"),
    key_type: str | None = Query(None, description="Filter by type: master, connector, webhook, api, pii"),
    tenant_id: str | None = Query(None),
    include_revoked: bool = Query(False),
    user: User = Depends(_require_encryption_admin),
):
    """List all registered encryption keys."""
    state_enum = KeyState(state) if state else None
    type_enum = KeyType(key_type) if key_type else None

    registry = get_key_registry()
    keys = await registry.list_keys(
        state=state_enum,
        key_type=type_enum,
        tenant_id=tenant_id,
        include_revoked=include_revoked,
    )

    return {"keys": keys, "count": len(keys), "timestamp": datetime.now(UTC).isoformat()}


@router.get("/keys/{key_id}")
async def get_key(
    key_id: str,
    user: User = Depends(_require_encryption_admin),
):
    """Get details of a specific key."""
    registry = get_key_registry()
    key = await registry.get_key(key_id)

    if not key:
        raise HTTPException(status_code=404, detail="Anahtar bulunamadi")

    return {**key, "timestamp": datetime.now(UTC).isoformat()}


@router.get("/keys/{key_id}/summary")
async def get_key_summary(
    key_id: str,
    user: User = Depends(_require_encryption_admin),
):
    """Get safe summary of a key (no sensitive details)."""
    registry = get_key_registry()
    summary = await registry.get_safe_summary(key_id)

    if "error" in summary:
        raise HTTPException(status_code=404, detail=summary["error"])

    return {**summary, "timestamp": datetime.now(UTC).isoformat()}


@router.get("/keys/active/{key_type}")
async def get_active_key(
    key_type: str,
    tenant_id: str = Query(""),
    provider: str = Query(""),
    user: User = Depends(_require_encryption_admin),
):
    """Get the currently active key for a type/tenant/provider combination."""
    try:
        type_enum = KeyType(key_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Gecersiz key_type: {key_type}")

    registry = get_key_registry()
    key = await registry.get_active_key(type_enum, tenant_id, provider)

    if not key:
        raise HTTPException(status_code=404, detail="Aktif anahtar bulunamadi")

    return {**key, "timestamp": datetime.now(UTC).isoformat()}


# ── Key State Management ───────────────────────────────────────────


@router.post("/keys/rotation/initiate")
async def initiate_rotation(
    body: InitiateRotationRequest,
    user: User = Depends(_require_encryption_admin),
):
    """Start key rotation process. Key moves to pending_rotation state."""
    registry = get_key_registry()
    result = await registry.initiate_rotation(
        body.key_id,
        actor=user.email,
        reason=body.reason,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Rotasyon baslatilamadi"))

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/keys/rotation/complete")
async def complete_rotation(
    body: CompleteRotationRequest,
    user: User = Depends(_require_encryption_admin),
):
    """Complete key rotation. Key moves to retired state."""
    registry = get_key_registry()
    result = await registry.complete_rotation(
        body.key_id,
        actor=user.email,
        new_version=body.new_version,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Rotasyon tamamlanamadi"))

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/keys/rotation/cancel")
async def cancel_rotation(
    body: CancelRotationRequest,
    user: User = Depends(_require_encryption_admin),
):
    """Cancel rotation and return key to active state."""
    registry = get_key_registry()
    result = await registry.cancel_rotation(
        body.key_id,
        actor=user.email,
        reason=body.reason,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Rotasyon iptal edilemedi"))

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/keys/emergency-revoke")
async def emergency_revoke(
    body: EmergencyRevokeRequest,
    user: User = Depends(_require_encryption_admin),
):
    """EMERGENCY: Immediately revoke a key. Cannot be undone.

    This is a critical security operation that should only be used
    when a key is compromised or suspected to be compromised.
    """
    if not body.reason or len(body.reason) < 10:
        raise HTTPException(
            status_code=400,
            detail="Acil iptal icin detayli sebep gerekli (min 10 karakter)",
        )

    registry = get_key_registry()
    result = await registry.emergency_revoke(
        body.key_id,
        actor=user.email,
        reason=body.reason,
        notify_channels=body.notify_channels,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "İptal başarısız"))

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


# ── Re-encryption Jobs ─────────────────────────────────────────────


@router.post("/reencryption/create")
async def create_reencryption_job(
    body: CreateReencryptionJobRequest,
    user: User = Depends(_require_encryption_admin),
):
    """Create a re-encryption job for migrating data to new key."""
    if not body.collections:
        raise HTTPException(status_code=400, detail="En az bir koleksiyon secilmeli")

    worker = get_reencryption_worker()
    result = await worker.create_job(
        key_id=body.key_id,
        collections=body.collections,
        actor=user.email,
        batch_size=body.batch_size,
        description=body.description,
    )

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/reencryption/start")
async def start_reencryption_job(
    body: JobActionRequest,
    user: User = Depends(_require_encryption_admin),
):
    """Start or resume a re-encryption job."""
    worker = get_reencryption_worker()
    result = await worker.start_job(body.job_id, actor=user.email)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Is baslatilamadi"))

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/reencryption/pause")
async def pause_reencryption_job(
    body: JobActionRequest,
    user: User = Depends(_require_encryption_admin),
):
    """Pause a running re-encryption job."""
    worker = get_reencryption_worker()
    result = await worker.pause_job(body.job_id, actor=user.email)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Is durdurulamadi"))

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/reencryption/cancel")
async def cancel_reencryption_job(
    body: JobActionRequest,
    user: User = Depends(_require_encryption_admin),
):
    """Cancel a re-encryption job."""
    worker = get_reencryption_worker()
    result = await worker.cancel_job(body.job_id, actor=user.email, reason=body.reason)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Is iptal edilemedi"))

    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.get("/reencryption/jobs")
async def list_reencryption_jobs(
    state: str | None = Query(None, description="Filter by state"),
    key_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(_require_encryption_admin),
):
    """List re-encryption jobs."""
    state_enum = JobState(state) if state else None

    worker = get_reencryption_worker()
    jobs = await worker.list_jobs(state=state_enum, key_id=key_id, limit=limit)

    return {"jobs": jobs, "count": len(jobs), "timestamp": datetime.now(UTC).isoformat()}


@router.get("/reencryption/jobs/{job_id}")
async def get_reencryption_job(
    job_id: str,
    user: User = Depends(_require_encryption_admin),
):
    """Get status of a specific re-encryption job."""
    worker = get_reencryption_worker()
    job = await worker.get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Is bulunamadi")

    return {**job, "timestamp": datetime.now(UTC).isoformat()}


# ── Dashboards ─────────────────────────────────────────────────────


@router.get("/dashboard")
async def get_encryption_dashboard(
    user: User = Depends(_require_encryption_admin),
):
    """Main encryption management dashboard.

    Shows key registry status, rotation schedule, re-encryption jobs.
    """
    registry = get_key_registry()
    worker = get_reencryption_worker()

    keys_dashboard = await registry.get_dashboard()
    jobs_dashboard = await worker.get_dashboard()

    return {
        "keys": keys_dashboard,
        "reencryption_jobs": jobs_dashboard,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/dashboard/keys")
async def get_keys_dashboard(
    user: User = Depends(_require_encryption_admin),
):
    """Key registry dashboard only."""
    registry = get_key_registry()
    return await registry.get_dashboard()


@router.get("/dashboard/jobs")
async def get_jobs_dashboard(
    user: User = Depends(_require_encryption_admin),
):
    """Re-encryption jobs dashboard only."""
    worker = get_reencryption_worker()
    return await worker.get_dashboard()


# ── Audit Logs ─────────────────────────────────────────────────────


@router.get("/audit/keys")
async def get_key_audit_log(
    key_id: str | None = Query(None),
    action: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    user: User = Depends(_require_encryption_admin),
):
    """Query key registry audit log."""
    registry = get_key_registry()
    return await registry.get_audit_log(
        key_id=key_id,
        action=action,
        severity=severity,
        limit=limit,
        skip=skip,
    )


@router.get("/audit/jobs")
async def get_job_audit_log(
    job_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(_require_encryption_admin),
):
    """Query re-encryption jobs audit log."""
    worker = get_reencryption_worker()
    return await worker.get_audit_log(job_id=job_id, limit=limit)


# ── Index Setup (called on startup) ────────────────────────────────


@router.post("/setup-indexes")
async def setup_indexes(
    user: User = Depends(_require_encryption_admin),
):
    """Create MongoDB indexes for encryption management collections."""
    registry = get_key_registry()
    worker = get_reencryption_worker()

    await registry.ensure_indexes()
    await worker.ensure_indexes()

    return {
        "status": "ok",
        "message": "Indeksler olusturuldu",
        "timestamp": datetime.now(UTC).isoformat(),
    }
