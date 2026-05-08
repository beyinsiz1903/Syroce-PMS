"""Af-sadakat (Omni Inbox Hub) integration endpoints.

- /api/integrations/afsadakat/launch (tenant user)  → SSO redirect
- /api/integrations/afsadakat/status (tenant user)  → connection state
- /api/integrations/afsadakat/webhook (Af-sadakat → us, API key auth)
- /api/integrations/afsadakat/admin/* (platform admin)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from core.afsadakat_provisioner import (
    AFSADAKAT_PRODUCT_KEY,
    build_launch_url,
    find_tenant_by_api_key,
    get_tenant_credentials,
    is_external_configured,
    mint_sso_token,
    provision_tenant,
    record_inbound_event,
)
from core.security import get_current_user
from core.subscriptions import tenant_has_module
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v93 DW

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations/afsadakat", tags=["af-sadakat"])


# ── Tenant: launch & status ─────────────────────────────────────
def _is_platform_super(user: User) -> bool:
    """Süper-admin / platform admin tüm tenant'larda Af-sadakat'a
    erişebilir — entitlement gate'i bu rollerde uygulanmaz."""
    from core.security import _is_super_admin
    if _is_super_admin(user):
        return True
    role = (user.role or "").lower()
    if role in ("super_admin", "platform_admin"):
        return True
    roles = getattr(user, "roles", None) or []
    return any((r or "").lower() in ("super_admin", "platform_admin") for r in roles)


@router.get("/status")
async def status(current_user: User = Depends(get_current_user)) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    is_super = _is_platform_super(current_user)
    has = await tenant_has_module(current_user.tenant_id, AFSADAKAT_PRODUCT_KEY)
    creds = await get_tenant_credentials(current_user.tenant_id)
    return {
        "entitled": bool(has or is_super),
        "entitlement_source": "super_admin" if (is_super and not has) else (
            "subscription" if has else "none"
        ),
        "provisioned": bool(creds and creds.get("status") == "active"),
        "mode": (creds or {}).get("mode"),
        "ext_tenant_id": (creds or {}).get("ext_tenant_id"),
        "external_configured": is_external_configured(),
    }


@router.post("/launch")
async def launch(current_user: User = Depends(get_current_user)) -> dict:
    """Mint an SSO token and return the Af-sadakat URL to open."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    is_super = _is_platform_super(current_user)
    if not is_super and not await tenant_has_module(
        current_user.tenant_id, AFSADAKAT_PRODUCT_KEY
    ):
        raise HTTPException(
            status_code=403,
            detail="Sadakat & Inbox modülü için aktif abonelik bulunamadı",
        )

    creds = await get_tenant_credentials(current_user.tenant_id)
    if not creds:
        # Lazy provision (e.g. legacy subscription that pre-dates this release)
        creds = await provision_tenant(current_user.tenant_id)

    sso_token = mint_sso_token(current_user.tenant_id, current_user.dict())
    url = build_launch_url(creds, sso_token)
    return {
        "url": url,
        "mode": creds.get("mode"),
        "external_ready": is_external_configured(),
        "expires_in_seconds": 120,
    }


# ── Inbound webhook (Af-sadakat → us) ───────────────────────────
@router.post("/webhook")
async def webhook(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """Receive events from Af-sadakat (loyalty.points_awarded, review.new,
    inbox.message_received, ...). Authenticated by tenant API key."""
    api_key = ""
    if authorization and authorization.lower().startswith("bearer "):
        api_key = authorization.split(" ", 1)[1].strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    creds = await find_tenant_by_api_key(api_key)
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        body = await request.json()
    except Exception:
        body = {}
    event_type = (body.get("event") or body.get("type") or "unknown").lower()
    payload = body.get("data") or body.get("payload") or body

    await record_inbound_event(creds["tenant_id"], event_type, payload)
    logger.info("[afsadakat] webhook tenant=%s event=%s",
                creds["tenant_id"], event_type)
    return {"ok": True}


# ── Platform admin ──────────────────────────────────────────────
def _require_platform_admin(user: User) -> None:
    from core.security import _is_super_admin
    if _is_super_admin(user):
        return
    role = (user.role or "").lower()
    if role in ("super_admin", "platform_admin"):
        return
    roles = getattr(user, "roles", None) or []
    if any(r in ("super_admin", "platform_admin") for r in roles):
        return
    raise HTTPException(status_code=403, detail="Platform admin gerekli")


class AdminProvisionIn(BaseModel):
    tenant_id: str


@router.post("/admin/provision")
async def admin_provision(
    payload: AdminProvisionIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
) -> dict:
    """Force-provision a tenant (e.g. retry after external Af-sadakat
    was misconfigured at first activation)."""
    _require_platform_admin(current_user)
    creds = await provision_tenant(payload.tenant_id)
    return {"ok": True, "credentials": {
        k: v for k, v in creds.items() if k != "api_key"
    }}


@router.get("/admin/tenants/{tenant_id}")
async def admin_get(
    tenant_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_platform_admin(current_user)
    creds = await get_tenant_credentials(tenant_id)
    if not creds:
        raise HTTPException(status_code=404, detail="Provisioning kaydı yok")
    # Don't leak the full api_key to admins; show only suffix
    safe = {**creds}
    if safe.get("api_key"):
        safe["api_key_suffix"] = safe["api_key"][-6:]
        safe.pop("api_key", None)
    return safe
