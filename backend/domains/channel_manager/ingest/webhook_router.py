"""
HotelRunner Webhook Router
===========================

Receives reservation webhooks from HotelRunner and persists as raw events.
ACKs immediately, processing happens asynchronously via ingest processor.

Endpoints:
  POST /api/channel-manager/hotelrunner/webhooks/reservations
  POST /api/channel-manager/hotelrunner/webhooks/modifications
  POST /api/channel-manager/hotelrunner/webhooks/cancellations
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    ConnectorProvider,
    ProcessingStatus,
    RawChannelEvent,
    RawEventSource,
)
from domains.channel_manager.ingest.normalizer import (
    extract_hotelrunner_identity,
)

logger = logging.getLogger("ingest.hotelrunner_webhooks")

router = APIRouter(
    prefix="/api/channel-manager/hotelrunner/webhooks",
    tags=["HotelRunner Webhooks"],
)


class WebhookResponse(BaseModel):
    status: str = "ok"
    event_id: str = ""
    message: str = ""


async def _persist_webhook(
    payload: dict[str, Any],
    event_type: str,
) -> str:
    """Persist a webhook payload as a raw event. Returns event_id."""
    # Extract identity
    identity = extract_hotelrunner_identity(payload)
    identity_with_type = {**identity}
    # Rebuild provider_event_id with event_type
    hr_number = identity.get("external_reservation_id", "")
    last_mod = identity.get("provider_last_modified_at", "")
    identity_with_type["provider_event_id"] = f"{hr_number}_{event_type}_{last_mod}"

    # Resolve tenant/property from connection
    # For now use payload fields or defaults — real impl matches via API key/token
    tenant_id = payload.get("tenant_id", "")
    property_id = payload.get("property_id", "")

    # If no tenant/property in payload, try to look up from connection
    if not tenant_id or not property_id:
        hr_id = payload.get("hr_id", "")
        if hr_id:
            # Attempt lookup
            connections = await repo.get_connections_by_tenant(tenant_id or "demo")
            for conn in connections:
                if conn.get("provider") == "hotelrunner":
                    tenant_id = conn.get("tenant_id", tenant_id)
                    property_id = conn.get("property_id", property_id)
                    break

    # Default fallback for testing
    if not tenant_id:
        tenant_id = "demo"
    if not property_id:
        property_id = "prop-001"

    # Compute hash
    payload_hash = RawChannelEvent.compute_payload_hash(payload)

    event = RawChannelEvent(
        tenant_id=tenant_id,
        property_id=property_id,
        provider=ConnectorProvider.HOTELRUNNER,
        event_type=event_type,
        provider_event_id=identity_with_type["provider_event_id"],
        external_reservation_id=identity_with_type["external_reservation_id"],
        provider_version=identity_with_type["provider_version"],
        provider_last_modified_at=identity_with_type["provider_last_modified_at"],
        raw_payload=payload,
        payload_hash=payload_hash,
        received_via=RawEventSource.WEBHOOK,
        processing_status=ProcessingStatus.PENDING,
    )

    event_id = await repo.insert_raw_event(event.to_doc())
    logger.info(f"HotelRunner webhook [{event_type}] persisted: {event_id} | ext_res={hr_number}")
    return event_id


@router.post("/reservations", response_model=WebhookResponse)
async def receive_reservation(request: Request):
    """Receive a new reservation webhook from HotelRunner."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = await _persist_webhook(payload, "reservation_create")
    return WebhookResponse(status="ok", event_id=event_id, message="Event received, processing queued")


@router.post("/modifications", response_model=WebhookResponse)
async def receive_modification(request: Request):
    """Receive a reservation modification webhook from HotelRunner."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = await _persist_webhook(payload, "reservation_modify")
    return WebhookResponse(status="ok", event_id=event_id, message="Event received, processing queued")


@router.post("/cancellations", response_model=WebhookResponse)
async def receive_cancellation(request: Request):
    """Receive a reservation cancellation webhook from HotelRunner."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Mark status as cancelled in payload for decision engine
    if "status" not in payload:
        payload["status"] = "cancelled"

    event_id = await _persist_webhook(payload, "reservation_cancel")
    return WebhookResponse(status="ok", event_id=event_id, message="Cancellation received, processing queued")
