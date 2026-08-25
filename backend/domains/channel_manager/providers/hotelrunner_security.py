import hashlib as _hashlib
import hmac as _hmac
import json
import logging
import os as _os
import time as _time

from fastapi import HTTPException, Request

from core.secrets import get_secrets_manager
from core.tenant_db import get_system_db

logger = logging.getLogger(__name__)

def _source_ip(request: Request) -> str:
    try:
        client = getattr(request, "client", None)
        return client.host if client else "unknown"
    except Exception:
        return "unknown"


def _log_webhook_reject(reason: str, source_ip: str, tenant_hint: str, hr_id_hint: str) -> None:
    """Structured security log for every rejected webhook.

    Records only fingerprints for request identifiers. Secret and signature
    material is never logged.
    """
    from core.masking import fingerprint_id
    masked_tenant = fingerprint_id(tenant_hint)
    masked_hr_id = fingerprint_id(hr_id_hint)
    masked_source = fingerprint_id(source_ip)
    logger.warning(
        "[HR-WEBHOOK][SECURITY] reject reason=%s source_fp=%s tenant_fp=%s hr_fp=%s",
        reason,
        masked_source,
        masked_tenant,
        masked_hr_id,
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
            if not hr_id_hint:
                hotel = body.get("hotel")
                if isinstance(hotel, dict):
                    hr_id_hint = (
                        hotel.get("hr_id")
                        or hotel.get("hotel_id")
                        or hotel.get("property_id")
                        or hotel.get("id")
                        or ""
                    )
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
        system_db = get_system_db()
        doc = await system_db.hotelrunner_connections.find_one(
            query,
            {"_id": 0, "tenant_id": 1, "hr_id": 1},
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
    req_id = request.scope.get("req_id", "unknown")
    if not hasattr(request.state, "hr_diag"):
        request.state.hr_diag = {}

    t_start = _time.time()
    request.state.hr_diag["request_received"] = t_start
    import logging
    _logger = logging.getLogger(__name__)
    _logger.info(f"[DIAG] [{req_id}] HR webhook request received")

    sig_header = (request.headers.get("X-HotelRunner-Signature") or request.headers.get("X-Signature") or "").strip()
    source_ip = _source_ip(request)
    t_body_start = _time.time()
    raw = await request.body()
    request.state.hr_diag["body_read_complete"] = _time.time()
    _logger.info(f"[DIAG] [{req_id}] Body read complete in {(_time.time() - t_body_start)*1000:.2f}ms")

    t_sig_start = _time.time()
    request.state.hr_diag["signature_verification_start"] = t_sig_start
    tenant_hint, hr_id_hint = _extract_signature_hints(request, raw)

    if not hr_id_hint:
        _log_webhook_reject("missing_headers", source_ip, tenant_hint, hr_id_hint)
        raise HTTPException(status_code=401, detail="Missing HotelRunner hr_id")

    t_resolve_start = _time.time()
    request.state.hr_diag["tenant_property_resolution_start"] = t_resolve_start
    conn = await _lookup_signing_connection(hr_id_hint)
    request.state.hr_diag["tenant_property_resolution_end"] = _time.time()
    _logger.info(f"[DIAG] [{req_id}] Tenant/property resolution took {(_time.time() - t_resolve_start)*1000:.2f}ms")

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

        secret_source = "missing"
        if per_property_secret:
            secret_source = "tenant credentials"
        elif global_secret:
            secret_source = "env"

        request.state.hr_diag["secret_source_type"] = secret_source
        _logger.info(f"[DIAG] [{req_id}] Secret source type: {secret_source}")

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
        request.state.hr_diag["signature_verification_end"] = _time.time()
        _logger.info(f"[DIAG] [{req_id}] Signature verification (HMAC) end in {(_time.time() - t_sig_start)*1000:.2f}ms")
        return

    # ── MODE 2: Official Callback Validation (Token + hr_id) ──

    # 1. Callback Secret Validation
    # Priority: SecretsManager > global environment secret. Plaintext
    # connection-document secrets are intentionally unsupported.
    sm = get_secrets_manager()
    tenant_id = conn.get("tenant_id") if conn else ""

    secret_manager_callback_secret = None
    if tenant_id and hr_id_hint:
        try:
            creds = await sm.get_provider_credentials(tenant_id, "hotelrunner", hr_id_hint)
            if creds:
                secret_manager_callback_secret = creds.get("callback_secret")
        except Exception:
            pass

    global_callback_secret = _os.environ.get("HOTELRUNNER_CALLBACK_SECRET")
    expected_secret = secret_manager_callback_secret or global_callback_secret

    secret_source = "missing"
    if secret_manager_callback_secret:
        secret_source = "tenant credentials"
    elif global_callback_secret:
        secret_source = "env"
    request.state.hr_diag["secret_source_type"] = secret_source
    _logger.info(f"[DIAG] [{req_id}] Secret source type: {secret_source}")

    # HotelRunner's official real-time push protocol authenticates callbacks
    # with token + hr_id. A callback path secret is an optional Syroce
    # defence-in-depth layer: enforce it only when one has been configured.
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

    if not real_token:
        raise HTTPException(status_code=503, detail="HotelRunner credentials not configured")

    if not _hmac.compare_digest(str(real_token), str(token)):
        _log_webhook_reject("invalid_token", source_ip, tenant_hint, hr_id_hint)
        raise HTTPException(status_code=401, detail="Invalid HotelRunner token")

    _bind_verified_tenant(request, conn)
    request.state.hr_diag["signature_verification_end"] = _time.time()
    _logger.info(f"[DIAG] [{req_id}] Signature verification (Token) end in {(_time.time() - t_sig_start)*1000:.2f}ms")


# ── Webhook Batch Processor ──────────────────────────────────────────
