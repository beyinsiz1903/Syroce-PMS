"""CapX integration admin router.

Super-admin only. Exposes status, manual sync, and test-event endpoints.
Booking lifecycle hooks (auto-push) live in a separate module (faz 2).
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.helpers import require_super_admin_guard
from integrations.capx import CapXError, get_capx_client

logger = logging.getLogger(__name__)
require_super_admin = require_super_admin_guard()

router = APIRouter(
    prefix="/api/capx",
    tags=["CapX Integration"],
    dependencies=[Depends(require_super_admin)],
)


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
    """Live connectivity test using a no-op HEAD-style call.

    Pushes an empty availability snapshot to verify Bearer token works.
    Returns CapX response or error detail without raising.
    """
    client = get_capx_client(refresh=True)
    if not client.configured:
        raise HTTPException(400, "CapX not configured (CAPX_BASE_URL + CAPX_API_KEY required)")

    # Minimal probe — try a small availability post; CapX should validate and
    # respond either OK or a structured 4xx that confirms auth works.
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
    """Manual availability push (for testing / one-off corrections)."""
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
    """Manual reservation event push (for testing HMAC signing)."""
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
