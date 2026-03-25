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
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response

from core.database import db

logger = logging.getLogger("exely.webhook")


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
    tenant_id: str, correlation_id: str, provider: str,
    external_id: str, event_type: str, raw_body: bytes,
    content_type: str, source_ip: str,
) -> str:
    """Store raw webhook payload for debugging. Returns payload_id."""
    payload_id = str(uuid.uuid4())
    try:
        await db.webhook_raw_payloads.insert_one({
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
        })
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
        "auth": "none (IP whitelist recommended)",
        "version": "1.0",
    }


@router.post("/reservations")
async def receive_reservation(request: Request):
    """Receive OTA_HotelResNotifRQ SOAP XML from Exely.

    Timeline stages written:
      1. webhook_received — raw SOAP payload stored
      2. normalized — XML parsed to structured data
      3. deduplicated — upsert result (new vs existing)
    """
    raw_body = await request.body()
    correlation_id = str(uuid.uuid4())
    source_ip = request.client.host if request.client else "unknown"
    t_start = datetime.now(UTC)

    if not raw_body or not raw_body.strip():
        return _xml_response(_soap_error_rs("Empty request body", "400"))

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
    except ET.ParseError as exc:
        await _timeline_append(
            tenant_id="unknown",
            correlation_id=correlation_id,
            entity_type="reservation",
            stage="webhook_received",
            status="failure",
            source="exely_webhook",
            provider="exely",
            metadata={
                "error": f"XML parse error: {exc}",
                "raw_payload_id": raw_payload_id,
                "source_ip": source_ip,
                "payload_size_bytes": len(raw_body),
            },
        )
        return _xml_response(_soap_error_rs(f"XML parse error: {exc}", "400"))

    try:
        data = _parse_reservation(root)
    except ValueError as exc:
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
    conn = await db.exely_connections.find_one(
        {"hotel_code": hotel_code}, {"_id": 0}
    )
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
        return _xml_response(
            _soap_error_rs(f"Unknown hotel code: {hotel_code} (404)", "404", echo_token)
        )

    tenant_id = conn.get("tenant_id", "")

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
        "commit": "confirmed", "cancel": "cancelled",
        "modify": "modified", "confirmed": "confirmed",
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
        ext_res_id, canonical_status, tenant_id, correlation_id[:8], is_new,
    )
    return _xml_response(_soap_success_rs(echo_token, ext_res_id))
