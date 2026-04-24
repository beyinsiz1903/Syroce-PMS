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
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from core.database import db
from core.security import get_current_user
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


# ── v106 Bug DAC (architect adversarial #6): inbound webhook signature
# verification. Mirrors the Resend hardening pattern. Without this an
# attacker who knew (or guessed) any tenant_id could forge create / modify /
# cancel reservation events at will (revenue corruption, fake bookings,
# channel-manager state poisoning). Fail-closed if secret is unset; explicit
# dev escape hatch via ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK=1.
async def _verify_hotelrunner_signature(request: Request) -> None:
    import hashlib as _hashlib
    import hmac as _hmac
    import os as _os
    import time as _time
    secret = _os.environ.get("HOTELRUNNER_WEBHOOK_SECRET")
    if not secret:
        if _os.environ.get("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK") != "1":
            raise HTTPException(
                status_code=503,
                detail="Webhook signing not configured (set HOTELRUNNER_WEBHOOK_SECRET)",
            )
        return
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
    raw = await request.body()
    signed_payload = f"{ts_header}.".encode() + raw
    expected = _hmac.new(secret.encode(), signed_payload, _hashlib.sha256).hexdigest()
    provided = sig_header.split("=", 1)[1] if "=" in sig_header else sig_header
    if not _hmac.compare_digest(expected, provided.lower()):
        raise HTTPException(status_code=401, detail="Invalid signature")


# ── Webhook Batch Processor ──────────────────────────────────────────

async def _process_webhook_batch(
    tenant_id: str, property_id: str, reservations: list, event_type: str,
    source_ip: str = "system",
):
    """Background task: process webhook reservations through ingest pipeline.
    Multi-room reservations are exploded into per-room pipeline events.
    """
    for res in reservations:
        try:
            sub_reservations = explode_multi_room_reservation(res)
            for sub_res in sub_reservations:
                try:
                    await _persist_and_process(tenant_id, property_id, sub_res, event_type, source_ip)
                except Exception as e:
                    logger.error(f"[WEBHOOK] Error processing sub-reservation {sub_res.get('hr_number')}: {e}")
        except Exception as e:
            logger.error(f"[WEBHOOK] Error processing {event_type}: {e}")


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
    """Resolve tenant_id from callback payload.

    Priority: header > query param > body > HR connection lookup by hr_id/token
    """
    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if tenant_id:
        return tenant_id

    tenant_id = body.get("tenant_id", "")
    if tenant_id:
        return tenant_id

    # Try to resolve from HR connection by hr_id
    hr_id = body.get("hr_id") or body.get("hotel_id") or body.get("property_id") or ""
    if hr_id:
        conn = await db.hotelrunner_connections.find_one(
            {"hr_id": str(hr_id), "is_active": True},
            {"_id": 0, "tenant_id": 1},
        )
        if conn:
            return conn["tenant_id"]

    # Try to resolve from any active HR connection (single-tenant fallback)
    conn = await db.hotelrunner_connections.find_one(
        {"is_active": True},
        {"_id": 0, "tenant_id": 1},
    )
    if conn:
        return conn["tenant_id"]

    return ""


# ── UNIFIED CALLBACK — Single endpoint for HotelRunner "Dönüş adresi" ──

@router.post("/callback")
async def unified_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    _sig: None = Depends(_verify_hotelrunner_signature),
):
    """
    Unified callback endpoint for HotelRunner webhook notifications.

    This is the single URL configured in HotelRunner panel as "Dönüş adresi".
    HotelRunner sends ALL events (new reservation, modification, cancellation)
    to this one URL. Event type is auto-detected from the payload's state field.

    Accepts: JSON payload from HotelRunner
    Returns: {"status": "accepted", "event_type": "...", "count": N}

    v106 Bug DAC follow-up (architect): /callback was the PRIMARY URL
    configured in the HR panel — previously left unsigned while
    /webhooks/{...} were patched. Same `_verify_hotelrunner_signature`
    helper applied here for parity (fail-closed without the env secret).
    """
    try:
        body = await request.json()
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

    logger.info(
        f"[CALLBACK] Received {event_type}: {len(reservations)} reservation(s) "
        f"from {source_ip}, tenant={tenant_id}"
    )

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, event_type, source_ip,
    )

    return {
        "status": "accepted",
        "event_type": event_type,
        "count": len(reservations),
        "message": f"{len(reservations)} rezervasyon alindi ({event_type})",
    }


# ── Webhook Endpoints ────────────────────────────────────────────────

@router.post("/webhooks/reservations")
async def webhook_reservations(
    request: Request,
    background_tasks: BackgroundTasks,
    _sig: None = Depends(_verify_hotelrunner_signature),
):
    """
    Webhook endpoint for new reservations from HotelRunner.
    Persists as raw_channel_event and processes via unified ingest pipeline.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required (header X-Tenant-ID or query param)")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_create", source_ip,
    )

    return {
        "status": "accepted",
        "count": len(reservations),
        "message": f"{len(reservations)} rezervasyon alindi, islenmeye baslandi",
    }


@router.post("/webhooks/modifications")
async def webhook_modifications(
    request: Request,
    background_tasks: BackgroundTasks,
    _sig: None = Depends(_verify_hotelrunner_signature),
):
    """Webhook for reservation modifications -> unified ingest pipeline."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_modify", source_ip,
    )
    return {"status": "accepted", "count": len(reservations)}


@router.post("/webhooks/cancellations")
async def webhook_cancellations(
    request: Request,
    background_tasks: BackgroundTasks,
    _sig: None = Depends(_verify_hotelrunner_signature),
):
    """Webhook for reservation cancellations -> unified ingest pipeline."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    # Set status to cancelled for the decision engine
    for res in reservations:
        if "status" not in res:
            res["status"] = "cancelled"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_cancel", source_ip,
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

    events = await db.hotelrunner_raw_events.find(
        query, {"_id": 0, "payload": 0}
    ).sort("received_at", -1).to_list(limit)
    return {"events": events, "count": len(events)}


@router.get("/logs/errors")
async def get_error_events(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """Get failed ingest events."""
    events = await db.hotelrunner_raw_events.find(
        {"tenant_id": current_user.tenant_id, "status": "error"},
        {"_id": 0},
    ).sort("received_at", -1).to_list(limit)
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
