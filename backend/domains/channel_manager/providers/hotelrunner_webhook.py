"""
HotelRunner Webhook Receiver

Lightweight receiver -> raw_channel_events -> async process via unified ingest pipeline.
Webhook endpoints for new reservations, modifications, and cancellations.
Raw event logs and replay API for debugging and audit.

UPDATED: Now feeds into the unified 9-collection ingest pipeline.
TIMELINE: Every webhook writes received -> normalized -> deduplicated stages.

UNIFIED CALLBACK: Single /callback endpoint for HotelRunner "Dönüş adresi" config.
HotelRunner sends ALL events (new, modify, cancel) to one URL — auto-detected via state field.
"""

import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from core.database import db
from core.security import get_current_user
from domains.channel_manager.providers.hotelrunner_security import (
    _verified_tenant,
    _verify_hotelrunner_callback,
)
from domains.channel_manager.providers.hotelrunner_shared import (
    _persist_and_process,
    _resolve_property_id,
    explode_multi_room_reservation,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v96 DW

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channel-manager/hotelrunner",
    tags=["HotelRunner Webhooks"],
)


# ── Per-property webhook signing helpers ─────────────────────────────
# Task #397: each hotel can hold its OWN encrypted webhook signing secret in
# the SecretsManager. The processed tenant is derived from the connection
# whose secret verifies the HMAC (cryptographic tenant binding), not from a
# client-supplied header/query/body value. A per-property secret takes
# precedence; the global HOTELRUNNER_WEBHOOK_SECRET remains a backward-compat
# fallback only when no per-property secret exists. Neither set → fail-closed.


async def _process_webhook_batch(
    tenant_id: str,
    property_id: str,
    reservations: list,
    event_type: str,
    source_ip: str = "system",
    req_id: str = "unknown",
):
    """Background task: process webhook reservations through ingest pipeline.
    Multi-room reservations are exploded into per-room pipeline events.
    """
    t_batch_start = time.time()
    logger.info(f"[DIAG] [{req_id}] batch_start: processing {len(reservations)} reservations")
    for res in reservations:
        try:
            sub_reservations = explode_multi_room_reservation(res)
            for sub_res in sub_reservations:
                t_persist_start = time.time()
                try:
                    logger.info(f"[DIAG] [{req_id}] persistence_start")
                    await _persist_and_process(tenant_id, property_id, sub_res, event_type, source_ip)
                    logger.info(f"[DIAG] [{req_id}] persistence_success elapsed_ms={(time.time() - t_persist_start)*1000:.2f}")
                except Exception as e:
                    logger.info(f"[DIAG] [{req_id}] persistence_failure exception_class={e.__class__.__name__} elapsed_ms={(time.time() - t_persist_start)*1000:.2f}")
                    from core.masking import fingerprint_id
                    masked_tenant = fingerprint_id(tenant_id)
                    masked_prop = fingerprint_id(property_id) if property_id else "none"
                    logger.error(f"[WEBHOOK] [{req_id}] Error processing sub-reservation event={event_type} exception_class={e.__class__.__name__} elapsed_ms={(time.time() - t_persist_start)*1000:.2f} tenant_fp={masked_tenant} prop_fp={masked_prop}")
        except Exception as e:
            from core.masking import fingerprint_id
            masked_tenant = fingerprint_id(tenant_id)
            masked_prop = fingerprint_id(property_id) if property_id else "none"
            logger.error(f"[WEBHOOK] [{req_id}] Error processing batch event={event_type} exception_class={e.__class__.__name__} tenant_fp={masked_tenant} prop_fp={masked_prop}")
    logger.info(f"[DIAG] [{req_id}] batch_end total_elapsed_ms={(time.time() - t_batch_start)*1000:.2f}")


def _detect_event_type(body: dict) -> str:
    """Auto-detect event type from HotelRunner callback payload.

    HotelRunner sends a single callback with reservation data.
    The event type is determined by the 'state' field:
      - new/confirmed/guaranteed -> reservation_create
      - modified -> reservation_modify
      - cancelled/canceled -> reservation_cancel
    Also checks 'action' or 'event_type' fields if present.
    """
    # Check explicit event_type or action field first
    explicit = body.get("event_type") or body.get("action") or ""
    if explicit:
        explicit_lower = explicit.lower()
        if "cancel" in explicit_lower:
            return "reservation_cancel"
        if "modif" in explicit_lower or "update" in explicit_lower:
            return "reservation_modify"
        if "create" in explicit_lower or "new" in explicit_lower:
            return "reservation_create"

    # Detect from reservation state
    state = (body.get("state") or "").lower()
    if state in ("cancelled", "canceled"):
        return "reservation_cancel"
    if state in ("modified",):
        return "reservation_modify"

    # Check cancel_reason presence
    if body.get("cancel_reason"):
        return "reservation_cancel"

    # Check reservations array if present
    reservations = body.get("reservations", [])
    if reservations and isinstance(reservations, list):
        first_res = reservations[0] if reservations else {}
        res_state = (first_res.get("state") or "").lower()
        if res_state in ("cancelled", "canceled"):
            return "reservation_cancel"
        if res_state in ("modified",):
            return "reservation_modify"

    # Default: new reservation
    return "reservation_create"


async def _resolve_tenant_from_callback(body: dict, request: Request) -> str:
    """Resolve tenant_id for the callback.

    Priority: signature-verified tenant (cryptographically bound).
    All insecure fallbacks have been removed.
    """
    bound = _verified_tenant(request)
    if bound:
        return bound
    return ""


async def _parse_payload(request: Request) -> dict:
    """Parse JSON from either direct body or x-www-form-urlencoded 'data' field."""
    try:
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            data_str = form.get("data")
            if not data_str:
                raise ValueError("Missing 'data' field in form")
            return json.loads(data_str)
        return await request.json()
    except Exception as e:
        req_id = request.scope.get("req_id", "unknown")
        logger.error(f"[WEBHOOK] [{req_id}] Payload parsing failed exception_class={e.__class__.__name__}")
        raise HTTPException(status_code=400, detail="Invalid payload format")


# ── UNIFIED CALLBACK — Single endpoint for HotelRunner "Dönüş adresi" ──


@router.post("/callback")
@router.post("/callback/{secret}")
async def unified_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    response: Response,
    _sig: None = Depends(_verify_hotelrunner_callback),
):
    """
    Unified callback endpoint for HotelRunner webhook notifications.

    This is the single URL configured in HotelRunner panel as "Dönüş adresi".
    HotelRunner sends ALL events (new reservation, modification, cancellation)
    to this one URL. Event type is auto-detected from the payload's state field.

    Accepts: JSON payload from HotelRunner
    Returns exactly {"status": "ok"}, as required by HotelRunner's REST
    real-time push acknowledgement contract. Processing details remain in the
    unified event log; returning an internal status such as ``accepted`` makes
    HotelRunner retry and eventually move the reservation to its email queue.

    v106 Bug DAC follow-up (architect): /callback was the PRIMARY URL
    configured in the HR panel — previously left unsigned while
    /webhooks/{...} were patched. Same `_verify_hotelrunner_signature`
    helper applied here for parity (fail-closed without the env secret).
    """
    try:
        body = await _parse_payload(request)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Resolve tenant
    tenant_id = await _resolve_tenant_from_callback(body, request)
    if not tenant_id:
        logger.error("[CALLBACK] Could not resolve tenant_id from callback payload")
        raise HTTPException(status_code=400, detail="tenant_id could not be resolved")

    # Auto-detect event type
    event_type = _detect_event_type(body)

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if body.get("hr_number") else [])
    source_ip = request.client.host if request.client else "unknown"

    # For cancellations, ensure status is set
    if event_type == "reservation_cancel":
        for res in reservations:
            if "status" not in res:
                res["status"] = "cancelled"

    from core.masking import fingerprint_id
    masked_tenant = fingerprint_id(tenant_id)
    logger.info(
        "[CALLBACK] Received event_type=%s count=%d tenant_fp=%s",
        event_type,
        len(reservations),
        masked_tenant,
    )

    req_id = request.scope.get("req_id", "unknown")
    t_enqueue_start = time.time()
    background_tasks.add_task(
        _process_webhook_batch,
        tenant_id,
        property_id,
        reservations,
        event_type,
        source_ip,
        req_id,
    )
    request.state.hr_diag["dispatch_end"] = time.time()
    logger.info(f"[DIAG] [{req_id}] background_task_enqueue_ms={(request.state.hr_diag['dispatch_end'] - t_enqueue_start)*1000:.2f}")

    total_duration = time.time() - request.state.hr_diag.get("request_received", time.time())
    logger.info(f"[DIAG] [{req_id}] Final response status 200, total duration {total_duration*1000:.2f}ms")

    return {"status": "ok"}


# ── Webhook Endpoints ────────────────────────────────────────────────


@router.post("/webhooks/reservations")
@router.post("/webhooks/reservations/{secret}")
async def webhook_reservations(
    request: Request,
    background_tasks: BackgroundTasks,
    response: Response,
    _sig: None = Depends(_verify_hotelrunner_callback),
):
    """
    Webhook endpoint for new reservations from HotelRunner.
    Persists as raw_channel_event and processes via unified ingest pipeline.
    """
    try:
        body = await _parse_payload(request)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = _verified_tenant(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Verified tenant binding required")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    req_id = request.scope.get("req_id", "unknown")
    t_enqueue_start = time.time()
    background_tasks.add_task(
        _process_webhook_batch,
        tenant_id,
        property_id,
        reservations,
        "reservation_create",
        source_ip,
        req_id,
    )
    request.state.hr_diag["dispatch_end"] = time.time()
    logger.info(f"[DIAG] [{req_id}] background_task_enqueue_ms={(request.state.hr_diag['dispatch_end'] - t_enqueue_start)*1000:.2f}")

    total_duration = time.time() - request.state.hr_diag.get("request_received", time.time())
    logger.info(f"[DIAG] [{req_id}] Final response status 200, total duration {total_duration*1000:.2f}ms")

    return {
        "status": "accepted",
        "count": len(reservations),
        "message": f"{len(reservations)} rezervasyon alindi, islenmeye baslandi",
    }


@router.post("/webhooks/modifications")
@router.post("/webhooks/modifications/{secret}")
async def webhook_modifications(
    request: Request,
    background_tasks: BackgroundTasks,
    _sig: None = Depends(_verify_hotelrunner_callback),
):
    """Webhook for reservation modifications -> unified ingest pipeline."""
    try:
        body = await _parse_payload(request)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = _verified_tenant(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Verified tenant binding required")
    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    background_tasks.add_task(
        _process_webhook_batch,
        tenant_id,
        property_id,
        reservations,
        "reservation_modify",
        source_ip,
    )
    return {"status": "accepted", "count": len(reservations)}


@router.post("/webhooks/cancellations")
@router.post("/webhooks/cancellations/{secret}")
async def webhook_cancellations(
    request: Request,
    background_tasks: BackgroundTasks,
    _sig: None = Depends(_verify_hotelrunner_callback),
):
    """Webhook for reservation cancellations -> unified ingest pipeline."""
    try:
        body = await _parse_payload(request)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = _verified_tenant(request)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Verified tenant binding required")
    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    # Set status to cancelled for the decision engine
    for res in reservations:
        if "status" not in res:
            res["status"] = "cancelled"

    background_tasks.add_task(
        _process_webhook_batch,
        tenant_id,
        property_id,
        reservations,
        "reservation_cancel",
        source_ip,
    )
    return {"status": "accepted", "count": len(reservations)}


# ── Raw Events API ───────────────────────────────────────────────────


@router.get("/logs/events")
async def get_raw_events(
    limit: int = 50,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get raw ingest events for debugging and audit."""
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status

    events = await db.hotelrunner_raw_events.find(query, {"_id": 0, "payload": 0}).sort("received_at", -1).to_list(limit)
    return {"events": events, "count": len(events)}


@router.get("/logs/errors")
async def get_error_events(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """Get failed ingest events."""
    events = (
        await db.hotelrunner_raw_events.find(
            {"tenant_id": current_user.tenant_id, "status": "error"},
            {"_id": 0},
        )
        .sort("received_at", -1)
        .to_list(limit)
    )
    return {"events": events, "count": len(events)}


@router.post("/sync/reservations/replay/{event_id}")
async def replay_event(
    event_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Replay a raw event through the ingest pipeline."""
    event = await db.hotelrunner_raw_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id},
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event bulunamadi")

    # v106 audit T03 spot-fix: defense-in-depth — tenant-scope the update.
    # find_one above already validates tenancy, but a TOCTOU re-tenant race
    # could otherwise let a stale write land cross-tenant. Also assert
    # matched_count to avoid silent no-op on race loss.
    res = await db.hotelrunner_raw_events.update_one(
        {"id": event_id, "tenant_id": current_user.tenant_id},
        {"$set": {"status": "pending", "processed_at": None, "error_message": None, "retry_count": (event.get("retry_count", 0) + 1)}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Event durumu degisti, tekrar deneyin")

    background_tasks.add_task(
        _process_webhook_batch,
        current_user.tenant_id,
        _resolve_property_id(event.get("payload", {})),
        [event["payload"]],
        event["event_type"],
    )
    return {"message": "Event replay baslatildi", "event_id": event_id}
