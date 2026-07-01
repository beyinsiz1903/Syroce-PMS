"""
Exely Webhook Router
====================
Receives OTA_HotelResNotifRQ SOAP push from Exely and ACKs with OTA_HotelResNotifRS.

Endpoints:
  GET  /api/webhooks/exely/health       — SOAP PingRS health check
  GET  /api/webhooks/exely/info         — Webhook configuration info (JSON)
  POST /api/webhooks/exely/reservations — OTA_HotelResNotifRQ ingest

TIMELINE INTEGRATION: Every webhook writes received → normalized → deduplicated
stages to the event timeline for full end-to-end traceability.
"""

import logging
import uuid
from datetime import UTC, datetime

# v109 Bug DAL round-7 (T11 CRITICAL XXE): inbound Exely SOAP webhook was
# previously parsed with stdlib xml.etree.ElementTree which resolves DOCTYPE
# external entities by default. An attacker reaching the webhook (post-IP-
# whitelist) could submit:
#   <!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
#   <OTA_HotelResNotifRQ><GivenName>&xxe;</GivenName>...</OTA_HotelResNotifRQ>
# and exfil server files via the parsed name fields, or pivot to internal
# SSRF (file://, http://localhost:..., gopher://, etc.). defusedxml disables
# entity resolution, DTD processing, and external references.
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from fastapi import APIRouter, Request
from fastapi.responses import Response

from core.database import db

logger = logging.getLogger("exely.webhook")


def _is_prod_env() -> bool:
    """True when running under a production-flagged environment."""
    import os

    _env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "").lower()
    return _env in ("production", "prod", "live")


def _exely_test_auth_open() -> bool:
    """Stress/E2E-only webhook IP-allowlist bypass — fail-closed multi-condition gate.

    Returns True ONLY when ALL of the following hold simultaneously, so a single
    stray env var can never open the webhook in production:
      * EXELY_TEST_WEBHOOK_AUTH_MODE == "open_for_testing"
      * environment is NOT production/prod/live
      * E2E_EXTERNAL_DRY_RUN == "true"         (outbound side-effects suppressed)
      * E2E_ALLOW_DESTRUCTIVE_STRESS == "true" (explicit destructive-stress opt-in)
      * E2E_STRESS_TENANT_ID is set non-empty  (stress tenant scoping present)

    This is intentionally SEPARATE from ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK (a
    single-flag dev escape hatch) which operator policy forbids using for the
    stress suite. The production default path remains fail-closed 503 — none of
    these conditions can be satisfied in a prod deployment without deliberately
    setting four test-only env vars in a non-prod environment.

    Tenant resolution is still performed server-side from the SOAP HotelCode →
    exely_connections lookup; the request body's tenant hints are never trusted.
    Additionally, while this bypass is active the resolved tenant is hard-bound
    to E2E_STRESS_TENANT_ID after lookup (see handler), so even a HotelCode that
    maps to another tenant in the same non-prod deployment is rejected — the
    bypass can only ever touch the stress tenant (pilot drift impossible).
    """
    import os

    if os.getenv("EXELY_TEST_WEBHOOK_AUTH_MODE") != "open_for_testing":
        return False
    if _is_prod_env():
        return False
    if (os.getenv("E2E_EXTERNAL_DRY_RUN") or "").lower() != "true":
        return False
    if (os.getenv("E2E_ALLOW_DESTRUCTIVE_STRESS") or "").lower() != "true":
        return False
    if not (os.getenv("E2E_STRESS_TENANT_ID") or "").strip():
        return False
    return True


def _exely_test_tenant_allowed(tenant_id: str) -> bool:
    """Tenant binding for the test-auth-open bypass.

    When the bypass removes the IP allowlist, the resolved tenant MUST equal
    E2E_STRESS_TENANT_ID. Any other tenant (e.g. a pilot tenant that happens to
    share the non-prod deployment) is rejected so the bypass can never mutate
    data outside the stress tenant. Fail-closed: blank/missing stress tenant or
    any mismatch returns False.
    """
    import os

    _stress_tid = (os.getenv("E2E_STRESS_TENANT_ID") or "").strip()
    if not _stress_tid:
        return False
    return (tenant_id or "").strip() == _stress_tid


def _timeline_append(**kwargs):
    """Fire-and-forget timeline write. Returns a coroutine."""
    try:
        from controlplane.timeline_writer import get_timeline_writer

        return get_timeline_writer().append(**kwargs)
    except Exception:

        async def _noop():
            return None

        return _noop()


async def _store_raw_payload(
    tenant_id: str,
    correlation_id: str,
    provider: str,
    external_id: str,
    event_type: str,
    raw_body: bytes,
    content_type: str,
    source_ip: str,
) -> str:
    """Store raw webhook payload for debugging. Returns payload_id."""
    payload_id = str(uuid.uuid4())
    try:
        await db.webhook_raw_payloads.insert_one(
            {
                "id": payload_id,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "provider": provider,
                "external_id": external_id,
                "event_type": event_type,
                "content_type": content_type,
                "raw_payload": raw_body.decode("utf-8", errors="replace"),
                "payload_size_bytes": len(raw_body),
                "source_ip": source_ip,
                "received_at": datetime.now(UTC).isoformat(),
            }
        )
    except Exception as e:
        logger.warning("Raw payload storage failed (non-blocking): %s", e)
    return payload_id


router = APIRouter(prefix="/api/webhooks/exely", tags=["Exely Webhooks"])

OTA_NS = "http://www.opentravel.org/OTA/2003/05"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


# ── Helpers ──────────────────────────────────────────────────────────


def _xml_response(body: str, status_code: int = 200) -> Response:
    return Response(content=body, media_type="text/xml; charset=utf-8", status_code=status_code)


def _soap_success_rs(echo_token: str = "", res_id: str = "") -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soap-env:Envelope xmlns:soap-env="{SOAP_NS}">'
        "<soap-env:Body>"
        f'<OTA_HotelResNotifRS xmlns="{OTA_NS}" EchoToken="{echo_token}" '
        f'TimeStamp="{ts}" Version="1.0">'
        "<Success/>"
        "</OTA_HotelResNotifRS>"
        "</soap-env:Body>"
        "</soap-env:Envelope>"
    )


def _soap_error_rs(message: str, code: str = "450", echo_token: str = "") -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soap-env:Envelope xmlns:soap-env="{SOAP_NS}">'
        "<soap-env:Body>"
        f'<OTA_HotelResNotifRS xmlns="{OTA_NS}" EchoToken="{echo_token}" '
        f'TimeStamp="{ts}" Version="1.0">'
        "<Errors>"
        f'<Error Type="3" Code="{code}">{message}</Error>'
        "</Errors>"
        "</OTA_HotelResNotifRS>"
        "</soap-env:Body>"
        "</soap-env:Envelope>"
    )


def _find(el, tag):
    """Find tag in element with or without OTA namespace."""
    found = el.find(f"{{{OTA_NS}}}{tag}")
    if found is None:
        found = el.find(tag)
    return found


def _findall(el, tag):
    found = el.findall(f"{{{OTA_NS}}}{tag}")
    if not found:
        found = el.findall(tag)
    return found


def _parse_reservation(root) -> dict:
    """Extract reservation data from OTA_HotelResNotifRQ XML tree."""
    body = root.find(f"{{{SOAP_NS}}}Body")
    if body is None:
        body = root.find("Body") or root

    rq = body.find(f"{{{OTA_NS}}}OTA_HotelResNotifRQ")
    if rq is None:
        rq = body.find("OTA_HotelResNotifRQ")
    if rq is None:
        for child in body:
            if "HotelResNotifRQ" in child.tag:
                rq = child
                break
    if rq is None:
        raise ValueError("Missing OTA_HotelResNotifRQ element")

    echo_token = rq.attrib.get("EchoToken", "")
    res_status = rq.attrib.get("ResStatus", "")

    reservations_el = _find(rq, "HotelReservations")
    if reservations_el is None:
        raise ValueError("Missing HotelReservations element")

    res_el = _find(reservations_el, "HotelReservation")
    if res_el is None:
        raise ValueError("Missing HotelReservation element")

    res_status = res_status or res_el.attrib.get("ResStatus", "Commit")
    create_dt = res_el.attrib.get("CreateDateTime", "")
    modify_dt = res_el.attrib.get("LastModifyDateTime", "")

    # UniqueID
    uid_el = _find(res_el, "UniqueID")
    reservation_id = uid_el.attrib.get("ID", "") if uid_el is not None else ""

    # RoomStay
    room_stays_el = _find(res_el, "RoomStays")
    hotel_code = ""
    checkin = ""
    checkout = ""
    room_type_code = ""
    total_amount = "0"
    currency = "TRY"

    if room_stays_el is not None:
        rs = _find(room_stays_el, "RoomStay")
        if rs is not None:
            bpi = _find(rs, "BasicPropertyInfo")
            if bpi is not None:
                hotel_code = bpi.attrib.get("HotelCode", "")
            ts = _find(rs, "TimeSpan")
            if ts is not None:
                checkin = ts.attrib.get("Start", "")
                checkout = ts.attrib.get("End", "")
            total_el = _find(rs, "Total")
            if total_el is not None:
                total_amount = total_el.attrib.get("AmountAfterTax", "0")
                currency = total_el.attrib.get("CurrencyCode", "TRY")
            rt_el = _find(rs, "RoomTypes")
            if rt_el is not None:
                rt = _find(rt_el, "RoomType")
                if rt is not None:
                    room_type_code = rt.attrib.get("RoomTypeCode", "")

    # Guest
    guest_first = ""
    guest_last = ""
    guest_email = ""
    guest_phone = ""
    res_guests = _find(res_el, "ResGuests")
    if res_guests is not None:
        rg = _find(res_guests, "ResGuest")
        if rg is not None:
            profiles = _find(rg, "Profiles")
            if profiles is not None:
                pi = _find(profiles, "ProfileInfo")
                if pi is not None:
                    prof = _find(pi, "Profile")
                    if prof is not None:
                        cust = _find(prof, "Customer")
                        if cust is not None:
                            pn = _find(cust, "PersonName")
                            if pn is not None:
                                gn = _find(pn, "GivenName")
                                sn = _find(pn, "Surname")
                                guest_first = gn.text if gn is not None and gn.text else ""
                                guest_last = sn.text if sn is not None and sn.text else ""
                            em = _find(cust, "Email")
                            if em is not None and em.text:
                                guest_email = em.text
                            tel = _find(cust, "Telephone")
                            if tel is not None:
                                guest_phone = tel.attrib.get("PhoneNumber", "")

    return {
        "echo_token": echo_token,
        "reservation_id": reservation_id,
        "res_status": res_status,
        "hotel_code": hotel_code,
        "checkin_date": checkin,
        "checkout_date": checkout,
        "room_type_code": room_type_code,
        "total_amount": total_amount,
        "currency": currency,
        "guest_first": guest_first,
        "guest_last": guest_last,
        "guest_name": f"{guest_first} {guest_last}".strip(),
        "guest_email": guest_email,
        "guest_phone": guest_phone,
        "create_datetime": create_dt,
        "last_modify_datetime": modify_dt,
    }


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/health")
async def webhook_health():
    """SOAP PingRS health check."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soap-env:Envelope xmlns:soap-env="{SOAP_NS}">'
        "<soap-env:Body>"
        f'<PingRS xmlns="{OTA_NS}" TimeStamp="{ts}">'
        "<Success/>"
        "</PingRS>"
        "</soap-env:Body>"
        "</soap-env:Envelope>"
    )
    return _xml_response(body)


@router.get("/info")
async def webhook_info():
    """Return webhook configuration as JSON."""
    return {
        "webhook_url": "/api/webhooks/exely/reservations",
        "method": "POST",
        "content_type": "text/xml; charset=utf-8",
        "supported_operations": [
            "OTA_HotelResNotifRQ",
            "OTA_CancelRQ",
            "OTA_HotelResModifyNotifRQ",
        ],
        "auth": "EXELY_IP_WHITELIST mandatory (ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1 dev escape; EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing is a fail-closed multi-condition stress/E2E-only bypass, prod stays 503)",
        "version": "1.0",
    }


@router.post("/reservations")
async def receive_reservation(request: Request):
    """Receive OTA_HotelResNotifRQ SOAP XML from Exely.

    Timeline stages written:
      1. webhook_received — raw SOAP payload stored
      2. normalized — XML parsed to structured data
      3. deduplicated — upsert result (new vs existing)

    Authentication (v106 Bug DAJ round-2 / architect adv. round #6):
      MANDATORY source-IP allowlist. The receiver previously fell open when
      EXELY_IP_WHITELIST was empty/unset → any anonymous attacker who knew a
      victim hotel's HotelCode (often public) could POST a forged OTA SOAP
      payload and inject reservations into that tenant's PMS (revenue fraud,
      channel-manager state poisoning). Now fail-closed unless either:
        * EXELY_IP_WHITELIST is set with the source IP, OR
        * ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1 (explicit dev escape hatch).
    """
    raw_body = await request.body()
    correlation_id = str(uuid.uuid4())
    t_start = datetime.now(UTC)

    # v109 Bug DAJ round-4/5 (architect P1 follow-up): proxy/IP trust.
    # request.client.host = *immediate* TCP peer. In any reverse-proxy/LB
    # deployment (DigitalOcean, nginx, ELB, Cloudflare) this is the proxy address,
    # NOT the real Exely SOAP client. Two attacker classes to defend against:
    #   (a) Whitelist contains proxy IP → any tenant of that proxy bypasses.
    #   (b) Whitelist contains real Exely IP but XFF is honored blindly →
    #       attacker can forge X-Forwarded-For: <exely-ip> from anywhere.
    # Round-5 hardening:
    #   1. EXELY_TRUST_FORWARDED=1 opt-in (default OFF — peer used).
    #   2. When opt-in, ONLY honor XFF if the immediate peer is in
    #      EXELY_TRUSTED_PROXY_IPS (comma list of IPs/CIDRs). Otherwise
    #      fall back to peer IP and forensic-log the rejection cause.
    #   3. Parse XFF rightward: rightmost-trusted is dropped, the IP just
    #      before the first untrusted hop is the real client (RFC 7239 §5.2
    #      semantics). Each token validated with ipaddress.ip_address.
    #   4. If EXELY_TRUST_FORWARDED=1 but EXELY_TRUSTED_PROXY_IPS unset, we
    #      DO NOT trust the header at all — guarded by startup guardrail
    #      that logs CRITICAL on this misconfiguration (see server.py).
    import ipaddress as _ipa
    import os

    def _parse_cidrs(spec: str):
        out = []
        for tok in spec.split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                out.append(_ipa.ip_network(tok, strict=False))
            except ValueError:
                logger.warning("Exely trusted-proxy entry invalid, skipped: %s", tok)
        return out

    def _ip_in(ip_str: str, nets) -> bool:
        try:
            ip = _ipa.ip_address(ip_str)
        except ValueError:
            return False
        return any(ip in n for n in nets)

    _peer = request.client.host if request.client else "unknown"
    source_ip = _peer
    _trust_forwarded = os.getenv("EXELY_TRUST_FORWARDED") == "1"
    _trusted_proxies_env = (os.getenv("EXELY_TRUSTED_PROXY_IPS") or "").strip()
    if _trust_forwarded and _trusted_proxies_env:
        _trusted_nets = _parse_cidrs(_trusted_proxies_env)
        if _trusted_nets and _ip_in(_peer, _trusted_nets):
            xff = (request.headers.get("X-Forwarded-For") or "").strip()
            if xff:
                # Walk rightward; drop trusted-proxy hops; first untrusted = client.
                tokens = [t.strip().lstrip("[").rstrip("]") for t in xff.split(",") if t.strip()]
                candidate = None
                for tok in reversed(tokens):
                    try:
                        _ipa.ip_address(tok)
                    except ValueError:
                        candidate = None
                        break
                    if _ip_in(tok, _trusted_nets):
                        continue
                    candidate = tok
                    break
                if candidate:
                    source_ip = candidate
                # else: malformed/all-trusted → keep peer (fail-closed wrt allowlist)
        else:
            logger.warning(
                "Exely XFF ignored: peer=%s not in EXELY_TRUSTED_PROXY_IPS — using peer for allowlist",
                _peer,
            )
    elif _trust_forwarded and not _trusted_proxies_env:
        logger.warning(
            "Exely EXELY_TRUST_FORWARDED=1 but EXELY_TRUSTED_PROXY_IPS unset — XFF NOT honored, using peer=%s",
            _peer,
        )

    _allow = (os.getenv("EXELY_IP_WHITELIST") or "").strip()
    _bypass = os.getenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK") == "1"
    # Stress/E2E-only fail-closed bypass (W6-deferred): activates ONLY when the
    # full multi-condition gate holds in a NON-prod environment. This lets the
    # stress suite exercise the valid-payload + idempotency path (spec § 50 "G")
    # without weakening production (prod default stays fail-closed 503) and
    # without using the operator-forbidden ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK.
    _test_open = _exely_test_auth_open()
    if _test_open:
        logger.warning(
            "Exely webhook TEST-AUTH-OPEN active (EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing "
            "+ E2E dry-run + destructive-stress opt-in + stress tenant, non-prod) source_ip=%s "
            "— IP allowlist bypassed for stress/E2E ONLY; tenant still resolved server-side.",
            source_ip,
        )
    if not _bypass and not _test_open:
        if not _allow:
            logger.warning(
                "Exely webhook rejected: EXELY_IP_WHITELIST not configured (set whitelist or ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1 to bypass) source_ip=%s peer=%s",
                source_ip,
                _peer,
            )
            return _xml_response(
                _soap_error_rs("Webhook not configured (set EXELY_IP_WHITELIST)", "503"),
                status_code=503,
            )
        allowed = {ip.strip() for ip in _allow.split(",") if ip.strip()}
        if source_ip not in allowed:
            logger.warning(
                "Exely webhook rejected: source_ip=%s peer=%s not in allowlist (trust_forwarded=%s)",
                source_ip,
                _peer,
                os.getenv("EXELY_TRUST_FORWARDED", "0"),
            )
            return _xml_response(_soap_error_rs("Unauthorized source IP", "403"), status_code=403)

    if not raw_body or not raw_body.strip():
        # Transport-level malformed input (empty body) → HTTP 400. Business/
        # resource faults (unknown hotel, tenant binding) keep HTTP 200 + SOAP
        # fault per the OTA no-retry convention, but an empty/unparseable body
        # is a client transport error and must not return 2xx (would be an
        # ambiguous "success" status for invalid input).
        return _xml_response(_soap_error_rs("Empty request body", "400"), status_code=400)

    # v109 Bug DAL round-7 follow-up (architect P2): bound XML payload size
    # before parsing. Without this, an attacker past the IP allowlist can
    # POST a multi-MB document and hold a worker thread on parse + timeline
    # I/O, regardless of XXE protections (defusedxml still walks deep
    # element trees). 256 KiB easily covers real OTA reservation envelopes
    # (typical ≤ 30 KiB) with a generous safety margin. Override via
    # EXELY_MAX_PAYLOAD_BYTES if a partner needs larger.
    _max_bytes_raw = (os.getenv("EXELY_MAX_PAYLOAD_BYTES") or "").strip()
    try:
        _max_bytes = int(_max_bytes_raw) if _max_bytes_raw else 262144
    except ValueError:
        _max_bytes = 262144
    if len(raw_body) > _max_bytes:
        logger.warning(
            "Exely webhook rejected oversize payload [%s] from %s: %d bytes > %d limit",
            correlation_id,
            source_ip,
            len(raw_body),
            _max_bytes,
        )
        return _xml_response(
            _soap_error_rs(f"Payload too large (limit {_max_bytes} bytes)", "413"),
            status_code=413,
        )

    # ── Stage 1: RECEIVED — store raw payload ────────────────────
    # Store raw payload immediately (even before parsing)
    raw_payload_id = await _store_raw_payload(
        tenant_id="pending",
        correlation_id=correlation_id,
        provider="exely",
        external_id="",
        event_type="reservation_webhook",
        raw_body=raw_body,
        content_type="text/xml",
        source_ip=source_ip,
    )

    try:
        root = ET.fromstring(raw_body)
    except (ET.ParseError, DefusedXmlException) as exc:
        # v109 Bug DAL round-7 (architect P2 follow-up): defusedxml raises
        # DefusedXmlException (EntitiesForbidden / DTDForbidden /
        # ExternalReferenceForbidden) for hostile XML. Without this catch the
        # handler returned 500, giving a low-effort DoS surface (any caller
        # past IP allowlist could crash the request with one malformed payload
        # and pollute error logs/alerts). Catch both ParseError and the
        # defusedxml hierarchy → return controlled SOAP 400.
        _is_security = isinstance(exc, DefusedXmlException)
        if _is_security:
            logger.warning(
                "Exely webhook rejected XXE/DTD payload [%s] from %s: %s",
                correlation_id,
                source_ip,
                type(exc).__name__,
            )
        await _timeline_append(
            tenant_id="unknown",
            correlation_id=correlation_id,
            entity_type="reservation",
            stage="webhook_received",
            status="failure",
            source="exely_webhook",
            provider="exely",
            metadata={
                "error": (f"XML security violation: {type(exc).__name__}" if _is_security else f"XML parse error: {exc}"),
                "raw_payload_id": raw_payload_id,
                "source_ip": source_ip,
                "payload_size_bytes": len(raw_body),
            },
        )
        # Do NOT echo defusedxml exception details back to the wire (could
        # leak server-side info about parser configuration). Generic message
        # for security violations; ParseError detail is safe to surface.
        # Transport-level malformed input (unparseable / hostile XML) → HTTP
        # 400, mirroring the empty-body case. Resource/business faults below
        # (unknown hotel code, tenant binding) deliberately stay HTTP 200 +
        # SOAP fault per the OTA no-retry convention.
        return _xml_response(
            _soap_error_rs(
                "XML security violation" if _is_security else f"XML parse error: {exc}",
                "400",
            ),
            status_code=400,
        )

    try:
        data = _parse_reservation(root)
    except ValueError as exc:
        # Well-formed XML that is missing required OTA structure (e.g. no
        # OTA_HotelResNotifRQ / HotelReservation) is a business/protocol-level
        # fault, not a transport-malformed body: the SOAP envelope parsed fine.
        # Per the OTA no-retry convention (and consistent with the unknown-hotel
        # and tenant-binding faults below) this returns HTTP 200 + SOAP fault,
        # NOT 400. Only empty/unparseable bodies above are HTTP 400.
        await _timeline_append(
            tenant_id="unknown",
            correlation_id=correlation_id,
            entity_type="reservation",
            stage="webhook_received",
            status="failure",
            source="exely_webhook",
            provider="exely",
            metadata={
                "error": str(exc),
                "raw_payload_id": raw_payload_id,
                "source_ip": source_ip,
            },
        )
        return _xml_response(_soap_error_rs(str(exc), "400"))

    hotel_code = data["hotel_code"]
    echo_token = data["echo_token"]
    ext_res_id = data["reservation_id"]

    # Resolve tenant by hotel_code
    conn = await db.exely_connections.find_one({"hotel_code": hotel_code}, {"_id": 0})
    if not conn:
        await _timeline_append(
            tenant_id="unknown",
            correlation_id=correlation_id,
            entity_type="reservation",
            external_id=ext_res_id,
            stage="webhook_received",
            status="failure",
            source="exely_webhook",
            provider="exely",
            metadata={
                "error": f"Unknown hotel code: {hotel_code}",
                "raw_payload_id": raw_payload_id,
                "hotel_code": hotel_code,
            },
        )
        return _xml_response(_soap_error_rs(f"Unknown hotel code: {hotel_code} (404)", "404", echo_token))

    tenant_id = conn.get("tenant_id", "")

    # When the stress/E2E test-auth bypass is active, hard-bind the resolved
    # tenant to E2E_STRESS_TENANT_ID. Without this, a request whose HotelCode
    # maps to ANY other tenant in the same non-prod deployment (e.g. a pilot
    # tenant) would be processed under the bypass. The IP-allowlist normally
    # provides that protection; since the bypass removes it, we reinstate the
    # boundary explicitly so the bypass can only ever touch the stress tenant
    # (pilot drift stays impossible). Defense-in-depth — outside the bypass
    # this check never runs, so production behavior is unchanged.
    if _test_open:
        if not _exely_test_tenant_allowed(tenant_id):
            logger.warning(
                "Exely TEST-AUTH-OPEN rejected: hotel_code=%s resolved tenant_id=%s != E2E_STRESS_TENANT_ID (cross-tenant blocked under stress bypass)",
                hotel_code,
                tenant_id,
            )
            await _timeline_append(
                tenant_id=tenant_id or "unknown",
                correlation_id=correlation_id,
                entity_type="reservation",
                external_id=ext_res_id,
                stage="webhook_received",
                status="failure",
                source="exely_webhook",
                provider="exely",
                metadata={
                    "error": "test-auth-open tenant binding violation",
                    "raw_payload_id": raw_payload_id,
                    "hotel_code": hotel_code,
                },
            )
            return _xml_response(_soap_error_rs(f"Unknown hotel code: {hotel_code} (404)", "404", echo_token))

    # Update raw payload with resolved tenant_id and external_id
    try:
        await db.webhook_raw_payloads.update_one(
            {"id": raw_payload_id},
            {"$set": {"tenant_id": tenant_id, "external_id": ext_res_id}},
        )
    except Exception:
        pass

    # Timeline: webhook_received (success)
    t_received = datetime.now(UTC)
    recv_duration_ms = int((t_received - t_start).total_seconds() * 1000)
    await _timeline_append(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        entity_type="reservation",
        external_id=ext_res_id,
        stage="webhook_received",
        status="success",
        source="exely_webhook",
        provider="exely",
        duration_ms=recv_duration_ms,
        metadata={
            "raw_payload_id": raw_payload_id,
            "hotel_code": hotel_code,
            "echo_token": echo_token,
            "source_ip": source_ip,
            "payload_size_bytes": len(raw_body),
            "content_type": "text/xml",
        },
    )

    # ── Stage 2: NORMALIZED — XML → structured data ──────────────
    now = datetime.now(UTC).isoformat()
    status_lower = (data["res_status"] or "commit").lower()
    canonical_status = {
        "commit": "confirmed",
        "cancel": "cancelled",
        "modify": "modified",
        "confirmed": "confirmed",
    }.get(status_lower, "confirmed")

    await _timeline_append(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        entity_type="reservation",
        external_id=ext_res_id,
        stage="normalized",
        status="success",
        source="exely_webhook",
        provider="exely",
        metadata={
            "guest_name": data["guest_name"],
            "checkin": data["checkin_date"],
            "checkout": data["checkout_date"],
            "room_type_code": data["room_type_code"],
            "total_amount": data["total_amount"],
            "currency": data["currency"],
            "canonical_status": canonical_status,
            "res_status_raw": data["res_status"],
        },
    )

    # ── Stage 3: DEDUPLICATE — upsert check ──────────────────────
    doc = {
        "external_id": ext_res_id,
        "tenant_id": tenant_id,
        "provider": "exely",
        "hotel_code": hotel_code,
        "guest_name": data["guest_name"],
        "guest_first": data["guest_first"],
        "guest_last": data["guest_last"],
        "guest_email": data["guest_email"],
        "guest_phone": data["guest_phone"],
        "checkin_date": data["checkin_date"],
        "checkout_date": data["checkout_date"],
        "room_type_code": data["room_type_code"],
        "total_amount": float(data["total_amount"]),
        "currency": data["currency"],
        "status": canonical_status,
        "source": "webhook",
        "correlation_id": correlation_id,
        "updated_at": now,
    }

    result = await db.exely_reservations.update_one(
        {"external_id": ext_res_id, "tenant_id": tenant_id},
        {"$set": doc, "$setOnInsert": {"created_at": now, "pms_status": "pending"}},
        upsert=True,
    )

    is_new = result.upserted_id is not None
    is_duplicate = not is_new

    await _timeline_append(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        entity_type="reservation",
        external_id=ext_res_id,
        stage="deduplicated",
        status="success",
        source="exely_webhook",
        provider="exely",
        metadata={
            "is_duplicate": is_duplicate,
            "is_new": is_new,
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "decision": "update_existing" if is_duplicate else "create_new",
            "canonical_status": canonical_status,
        },
    )

    logger.info(
        "Exely webhook reservation %s [%s] tenant=%s corr=%s new=%s",
        ext_res_id,
        canonical_status,
        tenant_id,
        correlation_id[:8],
        is_new,
    )
    return _xml_response(_soap_success_rs(echo_token, ext_res_id))
