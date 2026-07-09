import hashlib as _hashlib
import hmac as _hmac
import json
import logging
import os as _os
import time as _time

from fastapi import HTTPException, Request

from core.database import _raw_db
from core.secrets import get_secrets_manager

logger = logging.getLogger(__name__)

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
        doc = await _raw_db.hotelrunner_connections.find_one(
            query,
            {"_id": 0, "tenant_id": 1, "hr_id": 1, "callback_secret": 1, "token": 1},
        )
        logger.debug(
            "HotelRunner connection lookup completed found=%s",
            bool(doc),
        )
        return doc
    except Exception:
        logger.exception("Database error while looking up HotelRunner connection")
        raise HTTPException(status_code=503, detail="Webhook connection lookup unavailable")


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
        logger.exception("SecretsManager error while loading HotelRunner webhook secret")
        raise HTTPException(status_code=503, detail="Webhook credential service unavailable")


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
        if not conn:
            _log_webhook_reject("unknown_connection", source_ip, tenant_hint, hr_id_hint)
            raise HTTPException(status_code=401, detail="Connection not found")

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

        global_secret = _os.environ.get("HOTELRUNNER_WEBHOOK_SECRET")
        per_property_secret = await _load_webhook_secret(conn)
        active_secret = per_property_secret or global_secret

        if not active_secret:
            raise HTTPException(
                status_code=503,
                detail="Webhook signing not configured",
            )

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
    except Exception:
        logger.exception("SecretsManager error while loading HotelRunner token")
        raise HTTPException(status_code=503, detail="Webhook credential service unavailable")

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


