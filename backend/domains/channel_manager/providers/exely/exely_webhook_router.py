"""
Exely Webhook Router
====================
Receives OTA_HotelResNotifRQ SOAP push from Exely and ACKs with OTA_HotelResNotifRS.

Endpoints:
  GET  /api/webhooks/exely/health       — SOAP PingRS health check
  GET  /api/webhooks/exely/info         — Webhook configuration info (JSON)
  POST /api/webhooks/exely/reservations — OTA_HotelResNotifRQ ingest
"""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import Response

from core.database import db

logger = logging.getLogger("exely.webhook")

router = APIRouter(prefix="/api/webhooks/exely", tags=["Exely Webhooks"])

OTA_NS = "http://www.opentravel.org/OTA/2003/05"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


# ── Helpers ──────────────────────────────────────────────────────────

def _xml_response(body: str, status_code: int = 200) -> Response:
    return Response(content=body, media_type="text/xml; charset=utf-8", status_code=status_code)


def _soap_success_rs(echo_token: str = "", res_id: str = "") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    """Receive OTA_HotelResNotifRQ SOAP XML from Exely."""
    raw_body = await request.body()

    if not raw_body or not raw_body.strip():
        return _xml_response(_soap_error_rs("Empty request body", "400"))

    try:
        root = ET.fromstring(raw_body)
    except ET.ParseError as exc:
        return _xml_response(_soap_error_rs(f"XML parse error: {exc}", "400"))

    try:
        data = _parse_reservation(root)
    except ValueError as exc:
        return _xml_response(_soap_error_rs(str(exc), "400"))

    hotel_code = data["hotel_code"]
    echo_token = data["echo_token"]

    # Resolve tenant by hotel_code (no is_active filter — inbound webhooks
    # should always be accepted regardless of connection status)
    conn = await db.exely_connections.find_one(
        {"hotel_code": hotel_code}, {"_id": 0}
    )
    if not conn:
        return _xml_response(
            _soap_error_rs(f"Unknown hotel code: {hotel_code} (404)", "404", echo_token)
        )

    tenant_id = conn.get("tenant_id", "")

    # Upsert into exely_reservations (idempotent by external_id + tenant_id)
    now = datetime.now(timezone.utc).isoformat()
    status_lower = (data["res_status"] or "commit").lower()
    canonical_status = {
        "commit": "confirmed", "cancel": "cancelled",
        "modify": "modified", "confirmed": "confirmed",
    }.get(status_lower, "confirmed")

    doc = {
        "external_id": data["reservation_id"],
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
        "updated_at": now,
    }

    await db.exely_reservations.update_one(
        {"external_id": data["reservation_id"], "tenant_id": tenant_id},
        {"$set": doc, "$setOnInsert": {"created_at": now, "pms_status": "pending"}},
        upsert=True,
    )

    logger.info("Exely webhook reservation %s [%s] tenant=%s", data["reservation_id"], canonical_status, tenant_id)
    return _xml_response(_soap_success_rs(echo_token, data["reservation_id"]))
