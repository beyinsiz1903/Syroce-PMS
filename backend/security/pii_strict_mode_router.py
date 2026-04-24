"""
PII Strict Mode Router — API endpoints for managing PII enforcement.

Endpoints:
  GET  /api/security/pii-strict-mode/config   — Current config
  POST /api/security/pii-strict-mode/toggle    — Enable/disable
  POST /api/security/pii-strict-mode/whitelist — Update whitelisted paths
  GET  /api/security/pii-strict-mode/summary   — Violation summary
  GET  /api/security/pii-strict-mode/violations — Violation log
  GET  /api/security/pii-strict-mode/encryption-status — Field encryption coverage
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.cache import cached
from core.database import _raw_db as system_db
from core.security import get_current_user
from models.schemas import User
from security.field_encryption import get_field_encryption_service
from security.pii_registry import get_pii_policy_summary
from security.pii_strict_mode import get_pii_strict_mode_service

logger = logging.getLogger("security.pii_strict_mode_router")

router = APIRouter(
    prefix="/api/security/pii-strict-mode",
    tags=["Security — PII Strict Mode"],
)


def _require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Yetkisiz: admin veya super_admin rolu gerekli")
    return user


class ToggleRequest(BaseModel):
    enabled: bool


class WhitelistRequest(BaseModel):
    paths: list[str]


@router.get("/config")
async def get_config(user: User = Depends(_require_admin)):
    """Return current PII strict mode configuration."""
    svc = get_pii_strict_mode_service()
    config = await svc.get_config()
    return {"status": "ok", "config": config}


@router.post("/toggle")
async def toggle_strict_mode(body: ToggleRequest, user: User = Depends(_require_admin)):
    """Enable or disable PII strict mode globally."""
    svc = get_pii_strict_mode_service()
    config = await svc.toggle(
        enabled=body.enabled,
        actor=user.email,
        actor_role=user.role,
    )
    return {"status": "ok", "config": config}


@router.post("/whitelist")
async def update_whitelist(body: WhitelistRequest, user: User = Depends(_require_admin)):
    """Update whitelisted paths that bypass strict mode masking."""
    svc = get_pii_strict_mode_service()
    config = await svc.update_whitelist(paths=body.paths, actor=user.email)
    return {"status": "ok", "config": config}


@router.get("/summary")
async def get_summary(hours: int = 24, user: User = Depends(_require_admin)):
    """Return violation summary for the dashboard."""
    svc = get_pii_strict_mode_service()
    summary = await svc.get_summary(hours=hours)
    return {"status": "ok", "summary": summary}


@router.get("/violations")
async def get_violations(
    limit: int = 50,
    skip: int = 0,
    event_type: str | None = None,
    user: User = Depends(_require_admin),
):
    """Return PII violation event log."""
    svc = get_pii_strict_mode_service()
    result = await svc.get_violations(limit=limit, skip=skip, event_type=event_type)
    return {"status": "ok", **result}


# noqa: cache-rbac — _require_admin Depends zaten signature'da
@router.get("/encryption-status")
@cached(ttl=120, key_prefix="pii_encryption_status")
async def get_encryption_status(user: User = Depends(_require_admin)):
    """Return field-level encryption coverage per collection."""
    enc_svc = get_field_encryption_service()
    status = await enc_svc.get_encryption_status(system_db)
    return {
        "status": "ok",
        "collections": status,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/policy")
async def get_pii_policy(user: User = Depends(_require_admin)):
    """Return the full PII policy registry."""
    policy = get_pii_policy_summary()
    return {"status": "ok", "policy": policy}
