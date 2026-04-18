"""Af-sadakat (Omni Inbox Hub) provisioning + SSO helpers.

Two-mode operation:
- If AFSADAKAT_BASE_URL & AFSADAKAT_ADMIN_TOKEN are set in env, the
  PMS will call the external Af-sadakat instance to provision a tenant
  on first activation.
- Otherwise the system runs in 'local-only' mode: an API key is
  generated and stored locally so all the PMS-side plumbing (SSO
  endpoint, outbound APIs, webhook receiver) is testable end-to-end
  even before Af-sadakat is deployed.

Credentials live in the platform-wide collection
`integration_afsadakat_tenants` ({tenant_id, api_key, ext_tenant_id,
status, base_url, created_at, updated_at}).
"""
from __future__ import annotations

import os
import secrets
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

from core.security import JWT_SECRET, JWT_ALGORITHM

logger = logging.getLogger(__name__)

AFSADAKAT_PRODUCT_KEY = "af_sadakat"
SSO_TOKEN_TTL_SECONDS = 120  # short lived: only used for the redirect


def _db():
    from core.database import _raw_db
    return _raw_db


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def is_external_configured() -> bool:
    return bool(
        os.environ.get("AFSADAKAT_BASE_URL")
        and os.environ.get("AFSADAKAT_ADMIN_TOKEN")
    )


def get_external_base_url() -> str | None:
    return os.environ.get("AFSADAKAT_BASE_URL")


async def ensure_indexes() -> None:
    db = _db()
    try:
        await db.integration_afsadakat_tenants.create_index(
            "tenant_id", unique=True, name="uniq_afsadakat_tenant"
        )
        await db.integration_afsadakat_events.create_index(
            [("tenant_id", 1), ("received_at", -1)],
            name="idx_afsadakat_events"
        )
    except Exception:
        pass


async def get_tenant_credentials(tenant_id: str) -> dict[str, Any] | None:
    db = _db()
    return await db.integration_afsadakat_tenants.find_one(
        {"tenant_id": tenant_id}, {"_id": 0}
    )


async def find_tenant_by_api_key(api_key: str) -> dict[str, Any] | None:
    if not api_key:
        return None
    db = _db()
    return await db.integration_afsadakat_tenants.find_one(
        {"api_key": api_key, "status": "active"}, {"_id": 0}
    )


async def provision_tenant(tenant_id: str) -> dict[str, Any]:
    """Idempotent provisioning. Returns credentials dict.

    If external Af-sadakat is configured: calls its admin API to
    create/update a tenant and stores the returned credentials.
    Otherwise: generates a local API key and persists it.
    """
    db = _db()
    await ensure_indexes()

    # Atomically reserve a credentials row using $setOnInsert. Only the
    # winning concurrent caller actually gets to write a brand-new
    # api_key — everyone else reads back the winner's row and returns it.
    # This protects against api_key churn under concurrent activations.
    candidate_api_key = secrets.token_urlsafe(40)
    base_url = get_external_base_url()
    await db.integration_afsadakat_tenants.update_one(
        {"tenant_id": tenant_id},
        {
            "$setOnInsert": {
                "tenant_id": tenant_id,
                "api_key": candidate_api_key,
                "ext_tenant_id": None,
                "status": "active",
                "mode": "local",
                "base_url": base_url,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )
    existing = await get_tenant_credentials(tenant_id)
    if not existing:
        # Should be impossible after the upsert above.
        raise RuntimeError("afsadakat provisioning row vanished")

    api_key = existing["api_key"]
    is_first_time = api_key == candidate_api_key

    # Already fully provisioned (active + external resolved earlier or
    # explicitly local) — short-circuit. No external re-call, no churn.
    if not is_first_time and existing.get("status") == "active":
        logger.info("[afsadakat] tenant=%s already provisioned (mode=%s)",
                    tenant_id, existing.get("mode"))
        return existing

    ext_tenant_id: str | None = existing.get("ext_tenant_id")
    mode = existing.get("mode", "local")

    if is_first_time and is_external_configured():
        try:
            tenant_doc = await db.tenants.find_one(
                {"id": tenant_id},
                {"_id": 0, "property_name": 1, "email": 1, "phone": 1, "hotel_id": 1},
            ) or {}
            payload = {
                "external_tenant_id": tenant_id,
                "name": tenant_doc.get("property_name") or "Syroce Otel",
                "email": tenant_doc.get("email"),
                "phone": tenant_doc.get("phone"),
                "hotel_id": tenant_doc.get("hotel_id"),
                "pms_callback_url": _pms_callback_base(),
                "pms_api_key": api_key,
            }
            headers = {
                "Authorization": f"Bearer {os.environ['AFSADAKAT_ADMIN_TOKEN']}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=15.0) as cli:
                r = await cli.post(
                    f"{base_url.rstrip('/')}/api/admin/integrations/syroce/provision",
                    json=payload,
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json() or {}
                ext_tenant_id = data.get("ext_tenant_id") or data.get("tenant_id")
                mode = "external"
                logger.info("[afsadakat] external provisioning ok tenant=%s ext=%s",
                            tenant_id, ext_tenant_id)
        except Exception as e:
            # Don't block activation: keep local mode and let admin retry
            logger.warning("[afsadakat] external provision failed for %s: %s "
                           "(falling back to local mode)", tenant_id, e)

    doc = {
        "tenant_id": tenant_id,
        "api_key": api_key,
        "ext_tenant_id": ext_tenant_id,
        "status": "active",
        "mode": mode,
        "base_url": base_url,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.integration_afsadakat_tenants.update_one(
        {"tenant_id": tenant_id},
        {"$set": doc},
        upsert=True,
    )
    return doc


def _pms_callback_base() -> str:
    return (
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("REPLIT_DEV_DOMAIN_HTTPS")
        or "http://localhost:8000"
    )


def mint_sso_token(tenant_id: str, user: dict[str, Any]) -> str:
    """Short-lived signed token Af-sadakat will exchange for a session.

    Subject = tenant_id; includes user identity, role and email.
    """
    now = datetime.now(UTC)
    payload = {
        "iss": "syroce-pms",
        "aud": "afsadakat",
        "sub": tenant_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=SSO_TOKEN_TTL_SECONDS)).timestamp()),
        "user_id": user.get("id"),
        "username": user.get("username"),
        "name": user.get("name"),
        "email": user.get("email"),
        "role": user.get("role"),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def build_launch_url(creds: dict[str, Any], sso_token: str) -> str:
    base = (creds.get("base_url") or get_external_base_url() or "").rstrip("/")
    if not base:
        # Local-only mode: return our own placeholder route so the UI can
        # show a friendly "not yet deployed" page.
        return "/integrations/afsadakat/not-deployed"
    return f"{base}/sso/syroce?token={sso_token}"


async def record_inbound_event(
    tenant_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    db = _db()
    await ensure_indexes()
    await db.integration_afsadakat_events.insert_one({
        "tenant_id": tenant_id,
        "event_type": event_type,
        "payload": payload,
        "received_at": _now_iso(),
    })
