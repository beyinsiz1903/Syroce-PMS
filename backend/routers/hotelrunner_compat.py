"""
HotelRunner Integration Compatibility Router

Provides stable external-facing endpoints for HotelRunner panel configuration:
  GET  /api/integrations/hotelrunner/callback  — connection verification
  POST /api/integrations/hotelrunner/webhook   — unified webhook dispatcher

The POST endpoint inspects the payload's event_type/state and dispatches
to the internal ingest pipeline handlers (reservations/modifications/cancellations).
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/integrations/hotelrunner",
    tags=["HotelRunner External Integration"],
)


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
async def hotelrunner_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Unified HotelRunner webhook endpoint.
    Inspects payload to determine event type, then dispatches to the
    internal ingest pipeline (reservations / modifications / cancellations).
    """
    raw_body = await request.body()

    # v106 Bug DAC (architect adversarial #6): inbound webhook had NO signature
    # verification → an attacker who knew (or guessed) any tenant_id could
    # forge create/modify/cancel reservation events at will (revenue
    # corruption, fake bookings, channel-manager state poisoning). Mirror
    # the Resend webhook hardening: HMAC-SHA256 with replay protection,
    # fail-closed if secret is unset (dev escape via env flag).
    import os as _os
    secret = _os.environ.get("HOTELRUNNER_WEBHOOK_SECRET")
    if not secret:
        if _os.environ.get("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK") != "1":
            raise HTTPException(
                status_code=503,
                detail="Webhook signing not configured (set HOTELRUNNER_WEBHOOK_SECRET)",
            )
    else:
        import hmac as _hmac, hashlib as _hashlib, time as _time
        sig_header = (
            request.headers.get("X-HotelRunner-Signature")
            or request.headers.get("X-Signature")
            or ""
        ).strip()
        ts_header = (
            request.headers.get("X-HotelRunner-Timestamp")
            or request.headers.get("X-Timestamp")
            or ""
        ).strip()
        if not (sig_header and ts_header):
            raise HTTPException(status_code=401, detail="Missing signature headers")
        try:
            if abs(int(_time.time()) - int(ts_header)) > 300:
                raise HTTPException(status_code=401, detail="Timestamp out of tolerance")
        except (ValueError, TypeError):
            raise HTTPException(status_code=401, detail="Invalid timestamp")
        signed_payload = f"{ts_header}.".encode() + raw_body
        expected = _hmac.new(
            secret.encode(), signed_payload, _hashlib.sha256
        ).hexdigest()
        # Accept "sha256=<hex>" or bare hex
        provided = sig_header.split("=", 1)[1] if "=" in sig_header else sig_header
        if not _hmac.compare_digest(expected, provided.lower()):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        import json as _json
        body = _json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = (
        request.headers.get("X-Tenant-ID")
        or request.query_params.get("tenant_id")
        or body.get("tenant_id", "")
    )
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="tenant_id required (header X-Tenant-ID, query param, or body field)",
        )

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
                    tenant_id, property_id, res, pipeline_event_type, source_ip,
                )
            except Exception as e:
                logger.error("[COMPAT-WEBHOOK] Error processing %s: %s", pipeline_event_type, e)

    background_tasks.add_task(_process_batch)

    return {
        "status": "accepted",
        "event_type": pipeline_event_type,
        "count": len(reservations),
        "message": f"{len(reservations)} event accepted for processing",
    }
