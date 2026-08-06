"""
HotelRunner Integration Compatibility Router

Provides stable external-facing endpoints for HotelRunner panel configuration:
  GET  /api/integrations/hotelrunner/callback  — connection verification
  POST /api/integrations/hotelrunner/webhook   — unified webhook dispatcher

The POST endpoint inspects the payload's event_type/state and dispatches
to the internal ingest pipeline handlers (reservations/modifications/cancellations).
"""

import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from domains.channel_manager.providers.hotelrunner_security import (
    _verified_tenant,
    _verify_hotelrunner_callback,
)
from infra.production_config import is_production_env

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/integrations/hotelrunner",
    tags=["HotelRunner External Integration"],
)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _compatibility_webhook_enabled() -> bool:
    configured = os.environ.get("HOTELRUNNER_COMPAT_WEBHOOK_ENABLED")
    if configured is None:
        return not is_production_env()
    return configured.strip().lower() in _TRUE_VALUES


async def _verify_compatibility_webhook(request: Request) -> None:
    if not _compatibility_webhook_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    signature = (request.headers.get("X-HotelRunner-Signature") or request.headers.get("X-Signature") or "").strip()
    if not signature:
        raise HTTPException(status_code=401, detail="Signed webhook required")

    await _verify_hotelrunner_callback(request)
    if not _verified_tenant(request):
        raise HTTPException(status_code=401, detail="Verified tenant binding required")


@router.get("/callback")
async def hotelrunner_callback(request: Request):
    """
    HotelRunner callback verification endpoint.
    HotelRunner may call this with a challenge param to verify connectivity.
    """
    challenge = request.query_params.get("challenge", "")
    if challenge:
        return {"challenge": challenge}

    return {
        "status": "active",
        "provider": "syroce-pms",
        "version": "1.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "endpoints": {
            "callback": "/api/integrations/hotelrunner/callback",
            "webhook": "/api/integrations/hotelrunner/webhook",
        },
    }


def _detect_event_type(payload: dict) -> str:
    """
    Detect event type from HotelRunner webhook payload.
    Priority: explicit event_type field > state field > default.
    """
    explicit = (payload.get("event_type") or "").lower().strip()
    if explicit:
        if "cancel" in explicit:
            return "cancel"
        if "modif" in explicit or "update" in explicit:
            return "modify"
        return "create"

    state = (payload.get("state") or "").lower().strip()
    if state in ("cancelled", "canceled"):
        return "cancel"
    if state == "modified":
        return "modify"

    action = (payload.get("action") or "").lower().strip()
    if action:
        if "cancel" in action:
            return "cancel"
        if "modif" in action or "update" in action:
            return "modify"
        return "create"

    return "create"


@router.post("/webhook")
async def hotelrunner_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    _verification: None = Depends(_verify_compatibility_webhook),
):
    """
    Unified HotelRunner webhook endpoint.
    Inspects payload to determine event type, then dispatches to the
    internal ingest pipeline (reservations / modifications / cancellations).
    """
    raw_body = await request.body()

    try:
        import json as _json

        body = _json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = _verified_tenant(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Verified tenant binding required")

    reservations = body.get("reservations", [body] if body.get("hr_number") else [])
    if not reservations:
        raise HTTPException(status_code=400, detail="No reservation data in payload")

    property_id = body.get("property_id", "prop-001")
    source_ip = request.client.host if request.client else "unknown"

    from domains.channel_manager.providers.hotelrunner_shared import (
        _persist_and_process,
    )

    event_type = _detect_event_type(body)
    event_type_map = {
        "create": "reservation_create",
        "modify": "reservation_modify",
        "cancel": "reservation_cancel",
    }
    pipeline_event_type = event_type_map.get(event_type, "reservation_create")

    if event_type == "cancel":
        for res in reservations:
            if "status" not in res:
                res["status"] = "cancelled"

    async def _process_batch():
        for res in reservations:
            try:
                await _persist_and_process(
                    tenant_id,
                    property_id,
                    res,
                    pipeline_event_type,
                    source_ip,
                )
            except Exception as exc:
                logger.error(
                    "[COMPAT-WEBHOOK] Processing failed event_type=%s exception_class=%s",
                    pipeline_event_type,
                    type(exc).__name__,
                )

    background_tasks.add_task(_process_batch)

    return {
        "status": "accepted",
        "event_type": pipeline_event_type,
        "count": len(reservations),
        "message": f"{len(reservations)} event accepted for processing",
    }
