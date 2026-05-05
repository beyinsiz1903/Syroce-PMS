"""CapX integration admin router.

Super-admin only. Exposes status, manual sync, test-event, counter-offer ops,
and tenant credential management.
Booking lifecycle hooks (auto-push) live in integrations/capx/lifecycle.py.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.helpers import require_super_admin_guard
from core.security import get_current_user
from integrations.capx import (
    CapXError,
    delete_tenant_credentials,
    get_capx_client,
    get_capx_client_async,
    get_counter_offer,
    get_tenant_status,
    list_counter_offers,
    list_tenant_status,
    transition,
    upsert_tenant_credentials,
)

logger = logging.getLogger(__name__)
require_super_admin = require_super_admin_guard()

router = APIRouter(
    prefix="/api/capx",
    tags=["CapX Integration"],
    dependencies=[Depends(require_super_admin)],
)


# ── Pydantic models ──────────────────────────────────────────────

class AvailabilityPayload(BaseModel):
    room_type: str
    start_date: str
    end_date: str
    available_count: int = Field(ge=0)
    price_min: float = Field(ge=0)
    price_max: float | None = None
    currency: str = "TRY"
    auto_publish: bool = True
    pms_external_ref: str


class ReservationEventPayload(BaseModel):
    event_type: str = Field(pattern="^(created|cancelled|no_show)$")
    pms_external_ref: str
    booking_id: str
    guest_name: str | None = None
    check_in: str
    check_out: str
    amount: float | None = None
    currency: str = "TRY"


class CounterOfferDecision(BaseModel):
    notes: str = ""


class TenantCredentialUpsert(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    webhook_secret: str = ""


class CallbackRegisterPayload(BaseModel):
    callback_url: str | None = Field(
        default=None,
        description=(
            "PMS'in CapX'e bildireceği inbound webhook URL'si. Boş bırakılırsa "
            "REPLIT_DEV_DOMAIN/PUBLIC_BASE_URL üzerinden tenant-aware path "
            "(/api/webhooks/capx/by-tenant/{tenant_id}) otomatik üretilir."
        ),
    )
    tenant_id: str | None = Field(
        default=None,
        description="Hangi tenant'ın CapX kimliği ile çağrılacağı. Boş ise env fallback.",
    )
    jwt_token: str | None = Field(
        default=None,
        description=(
            "Otelin CapX hesabı için JWT (login token). Verilmezse Bearer api_key "
            "fallback denenir; spec §1 JWT bekliyor."
        ),
    )


# ── Status / Ping / Manual sync ──────────────────────────────────

@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Local config status — does not call CapX (use /ping for live check)."""
    client = get_capx_client(refresh=True)
    return {
        "configured": client.configured,
        "base_url_set": bool(client.base_url),
        "api_key_set": bool(client.api_key),
        "webhook_secret_set": bool(client.webhook_secret),
        "base_url": client.base_url or None,
    }


@router.post("/ping")
async def ping_capx() -> dict[str, Any]:
    """Live connectivity test using a small probe push."""
    client = get_capx_client(refresh=True)
    if not client.configured:
        raise HTTPException(400, "CapX not configured (CAPX_BASE_URL + CAPX_API_KEY required)")

    probe = {
        "room_type": "_PROBE_",
        "start_date": "2026-01-01",
        "end_date": "2026-01-02",
        "available_count": 0,
        "price_min": 0,
        "currency": "TRY",
        "auto_publish": False,
        "pms_external_ref": f"syroce-probe-{uuid.uuid4().hex[:8]}",
    }
    try:
        resp = await client.push_availability(probe)
        return {"ok": True, "response": resp}
    except CapXError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "status_code": exc.status_code,
            "body": exc.body,
        }


@router.post("/sync/availability")
async def sync_availability(payload: AvailabilityPayload) -> dict[str, Any]:
    """Manual availability push (testing / one-off corrections)."""
    client = get_capx_client(refresh=True)
    if not client.configured:
        raise HTTPException(400, "CapX not configured")
    try:
        resp = await client.push_availability(payload.model_dump(exclude_none=True))
        return {"ok": True, "response": resp}
    except CapXError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": str(exc), "status_code": exc.status_code, "body": exc.body},
        )


@router.post("/test-event")
async def test_reservation_event(payload: ReservationEventPayload) -> dict[str, Any]:
    """Manual reservation event push (testing HMAC signing)."""
    client = get_capx_client(refresh=True)
    if not client.configured or not client.webhook_secret:
        raise HTTPException(400, "CapX not configured (CAPX_WEBHOOK_SECRET required for events)")
    body = payload.model_dump(exclude_none=True)
    body["occurred_at"] = datetime.now(UTC).isoformat()
    try:
        resp = await client.push_reservation_event(body)
        return {"ok": True, "response": resp}
    except CapXError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": str(exc), "status_code": exc.status_code, "body": exc.body},
        )


# ── Counter-offer ops (Faz 3) ────────────────────────────────────

@router.get("/counter-offers")
async def list_offers(
    tenant_id: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(pending|accepted|rejected|expired)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    items = await list_counter_offers(tenant_id=tenant_id, status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/counter-offers/{offer_id}")
async def get_offer(offer_id: str) -> dict[str, Any]:
    offer = await get_counter_offer(offer_id)
    if not offer:
        raise HTTPException(404, "counter offer not found")
    return offer


async def _push_counter_decision(
    *, offer: dict[str, Any], decision: str,
) -> dict[str, Any]:
    """Karar verildikten sonra CapX'e push (best-effort, hata yutulur)."""
    tenant_id = offer.get("tenant_id")
    client = await get_capx_client_async(tenant_id=tenant_id)
    if not client.configured or not client.webhook_secret:
        return {"pushed": False, "reason": "client_not_configured"}

    body = {
        "event_type": f"counter_offer_{decision}",
        "pms_external_ref": offer.get("pms_external_ref"),
        "booking_id": offer.get("booking_id"),
        "counter_offer_id": offer.get("id"),
        "amount": offer.get("counter_amount") if decision == "accepted"
                  else offer.get("original_amount"),
        "currency": offer.get("currency", "TRY"),
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    event_id = f"co-{decision}-{offer.get('id', '')[:24]}"
    try:
        resp = await client.push_reservation_event(body, event_id=event_id)
        return {"pushed": True, "response": resp}
    except CapXError as exc:
        logger.warning("counter-offer %s push failed: %s", decision, exc)
        return {"pushed": False, "error": str(exc), "status_code": exc.status_code}


@router.post("/counter-offers/{offer_id}/accept")
async def accept_offer(
    offer_id: str,
    payload: CounterOfferDecision,
    user=Depends(get_current_user),
) -> dict[str, Any]:
    try:
        updated = await transition(
            offer_id=offer_id, new_status="accepted",
            actor_id=getattr(user, "id", "unknown"), notes=payload.notes,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))

    push_result = await _push_counter_decision(offer=updated, decision="accepted")
    return {"ok": True, "offer": updated, "push": push_result}


@router.post("/counter-offers/{offer_id}/reject")
async def reject_offer(
    offer_id: str,
    payload: CounterOfferDecision,
    user=Depends(get_current_user),
) -> dict[str, Any]:
    try:
        updated = await transition(
            offer_id=offer_id, new_status="rejected",
            actor_id=getattr(user, "id", "unknown"), notes=payload.notes,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))

    push_result = await _push_counter_decision(offer=updated, decision="rejected")
    return {"ok": True, "offer": updated, "push": push_result}


# ── Tenant credentials (Faz 3) ───────────────────────────────────

@router.get("/tenant-credentials")
async def list_tenant_creds() -> dict[str, Any]:
    items = await list_tenant_status()
    return {"items": items, "count": len(items)}


@router.get("/tenant-credentials/{tenant_id}")
async def get_tenant_creds(tenant_id: str) -> dict[str, Any]:
    return await get_tenant_status(tenant_id)


@router.put("/tenant-credentials/{tenant_id}")
async def upsert_tenant_creds(
    tenant_id: str,
    payload: TenantCredentialUpsert,
    user=Depends(get_current_user),
) -> dict[str, Any]:
    if payload.tenant_id != tenant_id:
        raise HTTPException(400, "tenant_id mismatch between path and body")
    return await upsert_tenant_credentials(
        tenant_id=tenant_id, base_url=payload.base_url, api_key=payload.api_key,
        webhook_secret=payload.webhook_secret, actor_id=getattr(user, "id", "unknown"),
    )


@router.delete("/tenant-credentials/{tenant_id}")
async def delete_tenant_creds(tenant_id: str) -> dict[str, Any]:
    return await delete_tenant_credentials(tenant_id)


# ── Callback URL register (CapX → PMS yönü) ──────────────────────

def _build_callback_url(tenant_id: str) -> str:
    """Public callback URL'i ortam değişkenlerinden üretir.

    Öncelik: PUBLIC_BASE_URL > REPLIT_DEV_DOMAIN (https eklenir) > localhost.
    """
    import os as _os
    base = _os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        dev = _os.getenv("REPLIT_DEV_DOMAIN", "").strip()
        if dev:
            base = f"https://{dev}".rstrip("/")
    if not base:
        base = "http://localhost:8000"
    return f"{base}/api/webhooks/capx/by-tenant/{tenant_id}"


@router.post("/callback/register")
async def register_callback(
    payload: CallbackRegisterPayload,
    user=Depends(get_current_user),
) -> dict[str, Any]:
    """PMS'in inbound webhook URL'sini CapX'e bildirir.

    Spec PMS_INCELEME_RAPORU.md §1: PUT {CAPX_BASE_URL}/api/integrations/v1/pms/callback
    body {"callback_url": "<PMS public webhook>"}.
    """
    tenant_id = payload.tenant_id or getattr(user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(400, "tenant_id required (payload veya kullanıcıdan)")

    callback_url = payload.callback_url or _build_callback_url(tenant_id)

    client = await get_capx_client_async(tenant_id=tenant_id)
    if not client.configured:
        raise HTTPException(400, "CapX yapılandırması eksik (CAPX_BASE_URL + API key)")

    try:
        resp = await client.register_callback(
            callback_url, jwt_token=payload.jwt_token,
        )
        return {
            "ok": True, "callback_url": callback_url,
            "tenant_id": tenant_id, "response": resp,
        }
    except CapXError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": str(exc),
                "status_code": exc.status_code,
                "body": exc.body,
                "callback_url": callback_url,
            },
        ) from exc


@router.get("/callback/url")
async def get_callback_url(
    tenant_id: str | None = Query(default=None),
    user=Depends(get_current_user),
) -> dict[str, Any]:
    """Hangi callback URL üretileceğini önizleme — PUT yapmadan."""
    effective = tenant_id or getattr(user, "tenant_id", None)
    if not effective:
        raise HTTPException(400, "tenant_id required")
    return {"tenant_id": effective, "callback_url": _build_callback_url(effective)}
