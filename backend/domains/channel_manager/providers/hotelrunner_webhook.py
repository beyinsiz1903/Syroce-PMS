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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from core.database import db
from core.secrets import get_secrets_manager
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


# ── Per-property webhook signing helpers ─────────────────────────────
# Task #397: each hotel can hold its OWN encrypted webhook signing secret in
# the SecretsManager. The processed tenant is derived from the connection
# whose secret verifies the HMAC (cryptographic tenant binding), not from a
# client-supplied header/query/body value. A per-property secret takes
# precedence; the global HOTELRUNNER_WEBHOOK_SECRET remains a backward-compat
# fallback only when no per-property secret exists. Neither set → fail-closed.


def _source_ip(request: Request) -> str:
    try:
        client = getattr(request, "client", None)
        return client.host if client else "unknown"
    except Exception:
        return "unknown"


def _log_webhook_reject(reason: str, source_ip: str, tenant_hint: str, hr_id_hint: str) -> None:
    """Structured security log for every rejected webhook.

    Records the source IP, the rejection reason and the (untrusted) tenant /
    hr_id hint. Secret and signature material is NEVER logged.
    """
    logger.warning(
        "[HR-WEBHOOK][SECURITY] reject reason=%s source_ip=%s tenant_hint=%s hr_id_hint=%s",
        reason,
        source_ip or "unknown",
        tenant_hint or "-",
        hr_id_hint or "-",
    )


def _extract_signature_hints(request: Request, raw: bytes) -> tuple[str, str]:
    """Pull the (untrusted) tenant / hr_id hints used only to LOCATE the
    candidate connection — never to authorize."""
    tenant_hint = ""
    hr_id_hint = ""
    
    qp = getattr(request, "query_params", None)
    if qp is not None:
        tenant_hint = qp.get("tenant_id") or ""
        hr_id_hint = qp.get("hr_id") or qp.get("hotel_id") or qp.get("property_id") or ""

    try:
        if not tenant_hint:
            tenant_hint = request.headers.get("X-Tenant-ID") or ""
    except Exception:
        pass

    import json
    try:
        body = {}
        content_type = request.headers.get("content-type", "")
        # Try to parse form-urlencoded payload for hints (P1 Fix)
        if "application/x-www-form-urlencoded" in content_type:
            try:
                # We can't await request.form() inside a sync func
                # Fortunately, Starlette caches request.form() but we can't await it here.
                # So we fallback to decoding raw manually for hints if needed.
                from urllib.parse import parse_qsl
                form_data = dict(parse_qsl(raw.decode("utf-8")))
                if not hr_id_hint:
                    hr_id_hint = form_data.get("hr_id") or ""
                data_str = form_data.get("data")
                if data_str:
                    body = json.loads(data_str)
            except Exception:
                pass
        else:
            body = json.loads(raw or b"{}")
            
        if isinstance(body, dict):
            if not tenant_hint:
                tenant_hint = body.get("tenant_id") or ""
            if not hr_id_hint:
                hr_id_hint = body.get("hr_id") or body.get("hotel_id") or body.get("property_id") or ""
    except Exception:
        pass
    return str(tenant_hint), str(hr_id_hint)


async def _lookup_signing_connection(hr_id_hint: str) -> dict | None:
    """Resolve the active connection that should govern this request from the
    untrusted hint. No hint → None (no DB hit), so the global-secret
    backward-compat path stays self-contained."""
    if not hr_id_hint:
        return None
    query: dict = {"is_active": True, "hr_id": str(hr_id_hint)}
    try:
        return await db.hotelrunner_connections.find_one(
            query,
            {"_id": 0, "tenant_id": 1, "hr_id": 1, "callback_secret": 1, "token": 1},
        )
    except Exception:
        return None


async def _load_webhook_secret(conn: dict) -> str | None:
    """Load the connection's per-property webhook signing secret (decrypted)
    from the SecretsManager. Returns None if none is configured."""
    tenant_id = conn.get("tenant_id")
    hr_id = conn.get("hr_id")
    if not (tenant_id and hr_id):
        return None
    try:
        sm = get_secrets_manager()
        return await sm.get_webhook_secret(tenant_id, "hotelrunner", str(hr_id))
    except Exception:
        return None


def _bind_verified_tenant(request: Request, conn: dict | None) -> None:
    """Bind the cryptographically-verified tenant onto request.state so the
    endpoints can use it instead of any client-supplied value."""
    if not (conn and conn.get("tenant_id")):
        return
    state = getattr(request, "state", None)
    if state is None:
        return
    try:
        state.hr_webhook_tenant_id = conn["tenant_id"]
    except Exception:
        pass


def _verified_tenant(request: Request) -> str:
    """Return the tenant bound by a verified signature, or empty string."""
    state = getattr(request, "state", None)
    if state is None:
        return ""
    return getattr(state, "hr_webhook_tenant_id", "") or ""


# ── v106 & Webhook Validation Refactor ───────────────────────────────
# Official HotelRunner documentation does not specify HMAC signature headers.
# Therefore, we support dual-mode validation:
# 1. Syroce Signed Webhook Mode (HMAC): Used internally and for secure mock tests.
#    Enabled if `X-HotelRunner-Signature` is present.
# 2. Official HotelRunner Callback Mode: Verifies `hr_id` and `token` against the DB,
#    and validates the `{secret}` path parameter if HOTELRUNNER_CALLBACK_SECRET is set.

async def _verify_hotelrunner_callback(request: Request) -> None:
    import hashlib as _hashlib
    import hmac as _hmac
    import os as _os
    import time as _time

    sig_header = (request.headers.get("X-HotelRunner-Signature") or request.headers.get("X-Signature") or "").strip()
    source_ip = _source_ip(request)
    raw = await request.body()
    tenant_hint, hr_id_hint = _extract_signature_hints(request, raw)

    if not hr_id_hint:
        _log_webhook_reject("missing_headers", source_ip, tenant_hint, hr_id_hint)
        raise HTTPException(status_code=401, detail="Missing HotelRunner hr_id")

    conn = await _lookup_signing_connection(hr_id_hint)

    if conn and not _hmac.compare_digest(str(conn["hr_id"]), str(hr_id_hint)):
        _log_webhook_reject("invalid_connection", source_ip, tenant_hint, hr_id_hint)
        raise HTTPException(status_code=401, detail="Connection ID mismatch")

    # ── MODE 1: HMAC Signature (Syroce Internal/Mock) ──
    if sig_header:
        global_secret = _os.environ.get("HOTELRUNNER_WEBHOOK_SECRET")
        per_property_secret = await _load_webhook_secret(conn) if conn else None
        active_secret = per_property_secret or global_secret

        if not active_secret:
            # P0 Fix: Removed ALLOW_UNSIGNED escape hatch entirely. Fail-closed if no secret.
            raise HTTPException(
                status_code=503,
                detail="Webhook signing not configured",
            )

        ts_header = (request.headers.get("X-HotelRunner-Timestamp") or request.headers.get("X-Timestamp") or "").strip()
        if not ts_header:
            _log_webhook_reject("missing_headers", source_ip, tenant_hint, hr_id_hint)
            raise HTTPException(status_code=401, detail="Missing signature headers")
        try:
            out_of_tolerance = abs(int(_time.time()) - int(ts_header)) > 300
        except (ValueError, TypeError):
            _log_webhook_reject("invalid_timestamp", source_ip, tenant_hint, hr_id_hint)
            raise HTTPException(status_code=401, detail="Invalid timestamp")
        if out_of_tolerance:
            _log_webhook_reject("stale_timestamp", source_ip, tenant_hint, hr_id_hint)
            raise HTTPException(status_code=401, detail="Timestamp out of tolerance")

        signed_payload = f"{ts_header}.".encode() + raw
        expected = _hmac.new(active_secret.encode(), signed_payload, _hashlib.sha256).hexdigest()
        provided = sig_header.split("=", 1)[1] if "=" in sig_header else sig_header
        if not _hmac.compare_digest(expected, provided.lower()):
            _log_webhook_reject("invalid_signature", source_ip, tenant_hint, hr_id_hint)
            raise HTTPException(status_code=401, detail="Invalid signature")

        _bind_verified_tenant(request, conn)
        return

    # ── MODE 2: Official Callback Validation (Token + hr_id + callback_secret) ──
    
    # 1. Callback Secret Validation
    # Prefer connection-specific callback secret, fallback to global
    global_callback_secret = _os.environ.get("HOTELRUNNER_CALLBACK_SECRET")
    connection_callback_secret = conn.get("callback_secret") if conn else None
    
    expected_secret = connection_callback_secret or global_callback_secret
    
    # P1 Fix: Fail closed in production if no secret is configured at all
    if _os.environ.get("APP_ENV") == "production" and not expected_secret:
        raise HTTPException(
            status_code=503,
            detail="HotelRunner callback secret not configured",
        )
        
    if expected_secret:
        path_secret = request.path_params.get("secret")
        if not path_secret or not _hmac.compare_digest(str(path_secret), str(expected_secret)):
            _log_webhook_reject("invalid_callback_secret", source_ip, tenant_hint, hr_id_hint)
            raise HTTPException(status_code=401, detail="Invalid callback secret")

    # 2. Token & HR_ID Extraction
    token = request.query_params.get("token")
    if not token:
        try:
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                token = form.get("token")
            else:
                import json
                body = json.loads(raw or b"{}")
                if isinstance(body, dict):
                    token = body.get("token")
        except Exception:
            pass

    if not token or not hr_id_hint:
        _log_webhook_reject("missing_official_credentials", source_ip, tenant_hint, hr_id_hint)
        raise HTTPException(status_code=401, detail="Missing hr_id or token for official validation")

    if not conn:
        _log_webhook_reject("unknown_connection", source_ip, tenant_hint, hr_id_hint)
        raise HTTPException(status_code=401, detail="Connection not found")

    # 3. Token Verification against SecretsManager
    real_token = None
    try:
        sm = get_secrets_manager()
        creds = await sm.get_provider_credentials(conn.get("tenant_id"), "hotelrunner", str(conn.get("hr_id")))
        if creds:
            real_token = creds.get("token")
    except Exception as e:
        logger.error(f"[WEBHOOK] Failed to load secrets for token validation: {e}")

    if not real_token and "token" in conn:
        if _os.environ.get("APP_ENV") in ("test", "development"):
            real_token = conn.get("token")
            logger.warning("[WEBHOOK] Security Warning: Falling back to plaintext DB token in test/dev mode.")

    if not real_token:
        # P1 Fix: Raise 503 instead of falling back to plaintext DB token in production
        raise HTTPException(status_code=503, detail="HotelRunner credentials not configured")

    if not _hmac.compare_digest(str(real_token), str(token)):
        _log_webhook_reject("invalid_token", source_ip, tenant_hint, hr_id_hint)
        raise HTTPException(status_code=401, detail="Invalid HotelRunner token")

    _bind_verified_tenant(request, conn)


# ── Webhook Batch Processor ──────────────────────────────────────────


async def _process_webhook_batch(
    tenant_id: str,
    property_id: str,
    reservations: list,
    event_type: str,
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
    """Resolve tenant_id for the callback.

    Priority: signature-verified tenant (cryptographically bound) > header >
    query param > body > HR connection lookup by hr_id.

    Task #397: the cryptographically-verified tenant always wins. The
    insecure "first active connection" fallback has been removed — a signed
    request that resolves no specific connection no longer leaks an arbitrary
    tenant identity.
    """
    bound = _verified_tenant(request)
    if bound:
        return bound

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
        logger.error(f"[WEBHOOK] Payload parsing failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload format")


# ── UNIFIED CALLBACK — Single endpoint for HotelRunner "Dönüş adresi" ──


@router.post("/callback")
@router.post("/callback/{secret}")
async def unified_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    _sig: None = Depends(_verify_hotelrunner_callback),
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

    logger.info(f"[CALLBACK] Received {event_type}: {len(reservations)} reservation(s) from {source_ip}, tenant={tenant_id}")

    background_tasks.add_task(
        _process_webhook_batch,
        tenant_id,
        property_id,
        reservations,
        event_type,
        source_ip,
    )

    return {
        "status": "accepted",
        "event_type": event_type,
        "count": len(reservations),
        "message": f"{len(reservations)} rezervasyon alindi ({event_type})",
    }


# ── Webhook Endpoints ────────────────────────────────────────────────


@router.post("/webhooks/reservations")
@router.post("/webhooks/reservations/{secret}")
async def webhook_reservations(
    request: Request,
    background_tasks: BackgroundTasks,
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

    tenant_id = _verified_tenant(request) or request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required (header X-Tenant-ID or query param)")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    background_tasks.add_task(
        _process_webhook_batch,
        tenant_id,
        property_id,
        reservations,
        "reservation_create",
        source_ip,
    )

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

    tenant_id = _verified_tenant(request) or request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

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

    tenant_id = _verified_tenant(request) or request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
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
