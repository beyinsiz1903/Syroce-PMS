"""
Secret Rotation Router — Safe rotation with test-before-switch and rollback.

Endpoints:
  POST /api/ops/secrets/rotation/initiate     — Create new version (pending test)
  POST /api/ops/secrets/rotation/test          — Dry-run test pending version
  POST /api/ops/secrets/rotation/activate      — Activate tested version
  POST /api/ops/secrets/rotation/rollback      — Rollback to previous version
  GET  /api/ops/secrets/rotation/status        — Version history for a secret
  GET  /api/ops/secrets/rotation/dashboard     — All secrets with expiration info
  GET  /api/ops/secrets/rotation/overdue       — Overdue secrets only
  GET  /api/ops/secrets/rotation/audit         — Rotation audit trail
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from security.ops_guard import require_ops_access

logger = logging.getLogger("security.rotation_router")

router = APIRouter(
    prefix="/api/ops/secrets/rotation",
    tags=["Security — Secret Rotation"],
    dependencies=[Depends(require_ops_access)],
)


# ── Request Models ─────────────────────────────────────────────────

class InitiateRotationRequest(BaseModel):
    secret_path: str
    new_credentials: dict[str, str]
    actor: str = "operator"
    tenant_id: str = ""
    provider: str = ""
    reason: str = "manual"


class TestRotationRequest(BaseModel):
    secret_path: str
    version: int
    actor: str = "operator"


class ActivateRotationRequest(BaseModel):
    secret_path: str
    version: int
    actor: str = "operator"


class RollbackRequest(BaseModel):
    secret_path: str
    target_version: int | None = None
    actor: str = "operator"


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/initiate")
async def initiate_rotation(body: InitiateRotationRequest):
    """Step 1: Create a new secret version (pending test).

    Does NOT activate. You must call /test then /activate.
    """
    from security.rotation_engine import get_rotation_engine

    engine = get_rotation_engine()
    result = await engine.initiate_rotation(
        secret_path=body.secret_path,
        new_credentials=body.new_credentials,
        actor=body.actor,
        tenant_id=body.tenant_id,
        provider=body.provider,
        reason=body.reason,
    )
    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/test")
async def test_rotation(body: TestRotationRequest):
    """Step 2: Dry-run test the pending version.

    For connector secrets, validates against the real provider API.
    """
    from security.rotation_engine import get_rotation_engine

    engine = get_rotation_engine()
    result = await engine.test_rotation(
        secret_path=body.secret_path,
        version=body.version,
        actor=body.actor,
    )
    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/activate")
async def activate_rotation(body: ActivateRotationRequest):
    """Step 3: Activate a tested version. Archives the previous active version.

    REQUIRES test_passed status. Will not activate untested versions.
    """
    from security.rotation_engine import get_rotation_engine

    engine = get_rotation_engine()
    result = await engine.activate_rotation(
        secret_path=body.secret_path,
        version=body.version,
        actor=body.actor,
    )
    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.post("/rollback")
async def rollback_rotation(body: RollbackRequest):
    """Rollback to a previous version. Single command, instant restore.

    If target_version is not specified, rolls back to the most recent archived version.
    """
    from security.rotation_engine import get_rotation_engine

    engine = get_rotation_engine()
    result = await engine.rollback(
        secret_path=body.secret_path,
        target_version=body.target_version,
        actor=body.actor,
    )
    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.get("/status")
async def rotation_status(
    secret_path: str = Query(..., description="Full secret path"),
):
    """Get full version history and rotation status for a secret."""
    from security.rotation_engine import get_rotation_engine

    engine = get_rotation_engine()
    result = await engine.get_rotation_status(secret_path)
    return {**result, "timestamp": datetime.now(UTC).isoformat()}


@router.get("/dashboard")
async def rotation_dashboard():
    """Rotation dashboard — all secrets with expiration status.

    Shows: active version, last rotation, next due, overdue flag.
    """
    from security.rotation_engine import get_rotation_engine

    engine = get_rotation_engine()
    return await engine.get_dashboard()


@router.get("/overdue")
async def overdue_secrets():
    """List secrets that are overdue for rotation."""
    from security.rotation_engine import get_rotation_engine

    engine = get_rotation_engine()
    return await engine.get_overdue_secrets()


@router.get("/audit")
async def rotation_audit(
    secret_path: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Query rotation-specific audit trail.

    Shows: who rotated what, when, test results, rollbacks.
    """
    from security.rotation_engine import get_rotation_engine

    engine = get_rotation_engine()
    return await engine.get_rotation_audit(
        secret_path=secret_path,
        tenant_id=tenant_id,
        limit=limit,
        skip=skip,
    )
