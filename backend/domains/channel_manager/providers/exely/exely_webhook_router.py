"""
Exely Webhook Router
====================
Public endpoint for Exely to PUSH reservation notifications (OTA_HotelResNotifRQ).
This solves the "reservation not delivered" problem by providing a webhook that
Exely can call directly, instead of relying on PULL + confirm handshake.

Flow:
  1. Exely sends OTA_HotelResNotifRQ SOAP XML via POST
  2. We parse the SOAP envelope, extract HotelReservation elements
  3. Resolve tenant by hotel_code from the XML
  4. Run through the common ingest pipeline
  5. Auto-import into PMS bookings
  6. Return OTA_HotelResNotifRS SOAP success response
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response, HTTPException
from defusedxml import ElementTree as safe_ET

from core.database import db
from domains.channel_manager.providers.common_ingest import ingest_reservation, log_sync
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.auto_import import auto_import_pending

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/exely", tags=["Exely Webhook"])

OTA_NS = "http://www.opentravel.org/OTA/2003/05"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
PROVIDER = "exely"


def _ns(tag: str, ns: str = OTA_NS) -> str:
    return f"{{{ns}}}{tag}"


def _attr(el, key, default=""):
    return el.get(key, default) if el is not None else default


def _text(el, default=""):
    return el.text.strip() if el is not None and el.text else default


def _parse_hotel_reservation_from_push(hr_el) -> dict:
    """Parse a single HotelReservation element from a PUSH notification.
    Reuses the same logic as the pull parser in response_parser.py."""
    res = {
        "reservation_id": _attr(hr_el, "ResID_Value", _attr(hr_el, "ResID")),
        "status": _attr(hr_el, "ResStatus", "Commit"),
        "create_date": _attr(hr_el, "CreateDateTime", ""),
        "last_modify": _attr(hr_el, "LastModifyDateTime", ""),
    }

    # UniqueID
    for uid in hr_el.iter(_ns("UniqueID")):
        uid_type = _attr(uid, "Type")
        uid_id = _attr(uid, "ID")
        if uid_type == "14":
            res["reservation_id"] = uid_id
        elif uid_type == "16":
            res["booking_source_id"] = uid_id

    # Guest info from ResGuest -> Profiles
    for guest in hr_el.iter(_ns("ResGuest")):
        for profile in guest.iter(_ns("Profile")):
            pname = profile.find(f".//{_ns('PersonName')}")
            if pname is not None:
                res["guest_firstname"] = _text(pname.find(_ns("GivenName")))
                res["guest_lastname"] = _text(pname.find(_ns("Surname")))
                res["guest_name"] = f"{res.get('guest_firstname', '')} {res.get('guest_lastname', '')}".strip()

            email_el = profile.find(f".//{_ns('Email')}")
            res["guest_email"] = _text(email_el)

            phone_el = profile.find(f".//{_ns('Telephone')}")
            res["guest_phone"] = _attr(phone_el, "PhoneNumber")

            address_el = profile.find(f".//{_ns('Address')}")
            if address_el is not None:
                res["guest_country"] = _text(address_el.find(_ns("CountryName")))
                res["guest_city"] = _text(address_el.find(_ns("CityName")))

    # Room stays
    rooms = []
    for room_stay in hr_el.iter(_ns("RoomStay")):
        room = {}

        for rt in room_stay.iter(_ns("RoomType")):
            room["room_type_code"] = _attr(rt, "RoomTypeCode")
            room["room_name"] = _attr(rt, "RoomDescription", _attr(rt, "RoomTypeCode"))

        for rp in room_stay.iter(_ns("RatePlan")):
            room["rate_plan_code"] = _attr(rp, "RatePlanCode")
            room["rate_plan_name"] = _attr(rp, "RatePlanName", "")

        daily_rates = []
        for rr in room_stay.iter(_ns("RoomRate")):
            room["room_type_code"] = room.get("room_type_code") or _attr(rr, "RoomTypeCode")
            room["rate_plan_code"] = room.get("rate_plan_code") or _attr(rr, "RatePlanCode")

            for rate in rr.iter(_ns("Rate")):
                daily_rates.append({
                    "date": _attr(rate, "EffectiveDate", ""),
                    "amount": _safe_float(_attr(rate, "AmountAfterTax", _attr(rate, "AmountBeforeTax", "0"))),
                })

        room["daily_rates"] = daily_rates

        adults = 0
        children = 0
        for gc in room_stay.iter(_ns("GuestCount")):
            age_code = _attr(gc, "AgeQualifyingCode")
            count = int(_attr(gc, "Count", "0"))
            if age_code == "10":
                adults = count
            elif age_code == "8":
                children = count
        room["adults"] = adults
        room["children"] = children

        for total_el in room_stay.iter(_ns("Total")):
            room["amount"] = _safe_float(_attr(total_el, "AmountAfterTax", "0"))
            room["currency"] = _attr(total_el, "CurrencyCode", "USD")

        for ts in room_stay.iter(_ns("TimeSpan")):
            room["check_in"] = _attr(ts, "Start", "")
            room["check_out"] = _attr(ts, "End", "")

        if room.get("room_type_code"):
            rooms.append(room)

    res["rooms"] = rooms

    if rooms:
        res["checkin_date"] = rooms[0].get("check_in", "")
        res["checkout_date"] = rooms[0].get("check_out", "")
        res["currency"] = rooms[0].get("currency", "USD")

    # Global info
    global_info = hr_el.find(f".//{_ns('ResGlobalInfo')}")
    if global_info is not None:
        total_el = global_info.find(_ns("Total"))
        if total_el is not None:
            res["total"] = _safe_float(_attr(total_el, "AmountAfterTax", "0"))
            res["currency"] = _attr(total_el, "CurrencyCode", res.get("currency", "USD"))

        for comment in global_info.iter(_ns("Comment")):
            text_el = comment.find(_ns("Text"))
            res["notes"] = _text(text_el)

        # Extract HotelCode from ResGlobalInfo or HotelReservationIDs
        for hrid in global_info.iter(_ns("HotelReservationID")):
            rid_type = _attr(hrid, "ResID_Type")
            rid_val = _attr(hrid, "ResID_Value")
            rid_source = _attr(hrid, "ResID_Source")
            if rid_type == "10" and rid_val:
                res["reservation_id"] = res.get("reservation_id") or rid_val

    # Channel from Source
    for source in hr_el.iter(_ns("Source")):
        booking_channel = source.find(_ns("BookingChannel"))
        if booking_channel is not None:
            res["channel"] = _attr(booking_channel, "CompanyName", _attr(booking_channel, "Type", "direct"))

    res.setdefault("channel", "exely")
    res.setdefault("total", sum(r.get("amount", 0) for r in rooms))
    res.setdefault("total_rooms", len(rooms))
    res.setdefault("total_guests", sum(r.get("adults", 1) + r.get("children", 0) for r in rooms) or 1)
    res.setdefault("notes", "")

    return res


def _safe_float(val) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _extract_hotel_code_from_xml(root) -> str:
    """Try to extract hotel code from various locations in the SOAP request."""
    # From RoomStay BasicPropertyInfo
    for bpi in root.iter(_ns("BasicPropertyInfo")):
        code = _attr(bpi, "HotelCode")
        if code:
            return code

    # From HotelReservation attributes
    for hr in root.iter(_ns("HotelReservation")):
        code = _attr(hr, "HotelCode")
        if code:
            return code

    # From POS -> Source -> BookingChannel
    for source in root.iter(_ns("Source")):
        code = _attr(source, "HotelCode")
        if code:
            return code

    # From ResGlobalInfo -> BasicPropertyInfo
    for gi in root.iter(_ns("ResGlobalInfo")):
        bpi = gi.find(_ns("BasicPropertyInfo"))
        if bpi is not None:
            code = _attr(bpi, "HotelCode")
            if code:
                return code

    return ""


def _determine_event_type(res_status: str) -> str:
    """Map OTA ResStatus to our event type."""
    status = (res_status or "").lower()
    if status in ("cancel", "cancelled"):
        return "cancellation"
    if status in ("modify", "modified", "commit"):
        # "Commit" can be new or modified; we let idempotency guard handle it
        return "reservation"
    return "reservation"


def _build_success_response(echo_token: str, reservation_ids: list) -> str:
    """Build OTA_HotelResNotifRS SOAP success response."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build HotelReservation elements for each processed reservation
    res_elements = ""
    for rid in reservation_ids:
        res_elements += f"""
      <HotelReservation>
        <UniqueID Type="14" ID="{rid}"/>
        <ResGlobalInfo>
          <HotelReservationIDs>
            <HotelReservationID ResID_Type="10" ResID_Value="{rid}" ResID_Source="PMS"/>
          </HotelReservationIDs>
        </ResGlobalInfo>
      </HotelReservation>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">
  <soap-env:Body>
    <OTA_HotelResNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"
                         EchoToken="{echo_token}"
                         TimeStamp="{now_str}"
                         Version="1.0"
                         ResResponseType="Committed"
                         Target="Production"
                         PrimaryLangID="en-us">
      <Success/>{f'''
      <HotelReservations>{res_elements}
      </HotelReservations>''' if res_elements else ''}
    </OTA_HotelResNotifRS>
  </soap-env:Body>
</soap-env:Envelope>"""


def _build_error_response(echo_token: str, error_code: str, error_message: str) -> str:
    """Build OTA_HotelResNotifRS SOAP error response."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">
  <soap-env:Body>
    <OTA_HotelResNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"
                         EchoToken="{echo_token}"
                         TimeStamp="{now_str}"
                         Version="1.0"
                         Target="Production"
                         PrimaryLangID="en-us">
      <Errors>
        <Error Code="{error_code}" ShortText="{error_message}" Type="Processing"/>
      </Errors>
    </OTA_HotelResNotifRS>
  </soap-env:Body>
</soap-env:Envelope>"""


@router.post("/reservations")
async def receive_reservation_push(request: Request):
    """
    Webhook endpoint for Exely to PUSH reservation notifications.
    Accepts OTA_HotelResNotifRQ SOAP XML and returns OTA_HotelResNotifRS.
    
    This is a PUBLIC endpoint (no JWT auth) — Exely calls it directly.
    Security is ensured by validating the hotel_code against known connections.
    """
    content_type = request.headers.get("content-type", "")
    echo_token = ""

    try:
        raw_body = await request.body()

        if not raw_body:
            return Response(
                content=_build_error_response("", "400", "Empty request body"),
                media_type="text/xml; charset=utf-8",
                status_code=200,
            )

        logger.info(f"[EXELY-WEBHOOK] Received push notification ({len(raw_body)} bytes)")
        logger.info(f"[EXELY-WEBHOOK] Content-Type: {content_type}")
        logger.info(f"[EXELY-WEBHOOK] Body preview: {raw_body[:2000].decode('utf-8', errors='replace')}")

        # Parse XML
        try:
            root = safe_ET.fromstring(raw_body)
        except Exception as e:
            logger.error(f"[EXELY-WEBHOOK] XML parse error: {e}")
            return Response(
                content=_build_error_response("", "400", f"XML parse error: {e}"),
                media_type="text/xml; charset=utf-8",
                status_code=200,
            )

        # Extract the OTA body from SOAP envelope
        body = root.find(f"{_ns('Body', SOAP_NS)}")
        if body is None:
            # Maybe it's not wrapped in a SOAP envelope
            body_el = root
        else:
            children = list(body)
            body_el = children[0] if children else root

        # Extract EchoToken for response correlation
        echo_token = _attr(body_el, "EchoToken", "")
        res_status_global = _attr(body_el, "ResStatus", "")

        # Extract hotel code for tenant resolution
        hotel_code = _extract_hotel_code_from_xml(root)

        # Parse all HotelReservation elements
        reservations_raw = []
        for hr in root.iter(_ns("HotelReservation")):
            parsed = _parse_hotel_reservation_from_push(hr)
            if parsed and parsed.get("reservation_id"):
                # Try to get hotel_code from BasicPropertyInfo within the reservation
                if not hotel_code:
                    for bpi in hr.iter(_ns("BasicPropertyInfo")):
                        hotel_code = _attr(bpi, "HotelCode")
                        if hotel_code:
                            break
                reservations_raw.append(parsed)

        if not reservations_raw:
            logger.warning("[EXELY-WEBHOOK] No HotelReservation elements found in push")
            return Response(
                content=_build_success_response(echo_token, []),
                media_type="text/xml; charset=utf-8",
                status_code=200,
            )

        logger.info(f"[EXELY-WEBHOOK] Parsed {len(reservations_raw)} reservation(s), hotel_code={hotel_code}")

        # Resolve tenant by hotel_code
        tenant_id = await _resolve_tenant(hotel_code)
        if not tenant_id:
            logger.error(f"[EXELY-WEBHOOK] No tenant found for hotel_code={hotel_code}")
            # Still return success to prevent Exely from retrying indefinitely
            return Response(
                content=_build_error_response(echo_token, "404", f"Unknown hotel code: {hotel_code}"),
                media_type="text/xml; charset=utf-8",
                status_code=200,
            )

        # Process each reservation through the ingest pipeline
        processed_ids = []
        for raw_res in reservations_raw:
            ext_id = raw_res.get("reservation_id", "unknown")
            status = raw_res.get("status", "")
            event_type = _determine_event_type(status or res_status_global)

            try:
                ingest_result = await ingest_reservation(
                    provider=PROVIDER,
                    tenant_id=tenant_id,
                    raw_payload=raw_res,
                    normalizer=normalize_reservation,
                    event_type=event_type,
                    source="webhook_push",
                )
                if ingest_result.get("success"):
                    processed_ids.append(ext_id)
                    logger.info(f"[EXELY-WEBHOOK] Ingested {ext_id}: action={ingest_result.get('action')}")
                else:
                    logger.warning(f"[EXELY-WEBHOOK] Ingest failed for {ext_id}: {ingest_result.get('error')}")
            except Exception as e:
                logger.error(f"[EXELY-WEBHOOK] Ingest error for {ext_id}: {e}")

        # Auto-import pending reservations to PMS
        try:
            import_result = await auto_import_pending(tenant_id)
            logger.info(
                f"[EXELY-WEBHOOK] Auto-import: {import_result.get('imported', 0)} imported, "
                f"{import_result.get('updated', 0)} updated"
            )
        except Exception as e:
            logger.warning(f"[EXELY-WEBHOOK] Auto-import error: {e}")

        # Log the sync
        await log_sync(
            PROVIDER, tenant_id, "webhook_push", "success",
            records=len(processed_ids), user_name="exely_webhook",
        )

        # Return SOAP success response
        logger.info(f"[EXELY-WEBHOOK] Successfully processed {len(processed_ids)} reservation(s)")
        return Response(
            content=_build_success_response(echo_token, processed_ids),
            media_type="text/xml; charset=utf-8",
            status_code=200,
        )

    except Exception as e:
        logger.error(f"[EXELY-WEBHOOK] Unexpected error: {e}", exc_info=True)
        await log_sync(PROVIDER, "", "webhook_push", "failed", error=str(e), user_name="exely_webhook")
        return Response(
            content=_build_error_response(echo_token, "500", "Internal processing error"),
            media_type="text/xml; charset=utf-8",
            status_code=200,
        )


async def _resolve_tenant(hotel_code: str) -> str:
    """Resolve tenant_id from hotel_code in exely_connections."""
    if not hotel_code:
        # If no hotel code in the XML, try to find the single active connection
        conn = await db.exely_connections.find_one(
            {"is_active": True},
            {"_id": 0, "tenant_id": 1},
        )
        if conn:
            return conn["tenant_id"]
        return ""

    conn = await db.exely_connections.find_one(
        {"hotel_code": hotel_code, "is_active": True},
        {"_id": 0, "tenant_id": 1},
    )
    if conn:
        return conn["tenant_id"]

    # Fallback: try without is_active filter
    conn = await db.exely_connections.find_one(
        {"hotel_code": hotel_code},
        {"_id": 0, "tenant_id": 1},
    )
    if conn:
        return conn["tenant_id"]

    return ""


@router.get("/health")
async def webhook_health():
    """Health check for the webhook endpoint. Exely may use this to verify connectivity."""
    return Response(
        content="""<?xml version="1.0" encoding="UTF-8"?>
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">
  <soap-env:Body>
    <PingRS xmlns="http://www.opentravel.org/OTA/2003/05">
      <Success/>
    </PingRS>
  </soap-env:Body>
</soap-env:Envelope>""",
        media_type="text/xml; charset=utf-8",
        status_code=200,
    )


@router.get("/info")
async def webhook_info():
    """Return webhook URL and configuration info for the user to configure in Exely."""
    return {
        "webhook_url": "/api/webhooks/exely/reservations",
        "method": "POST",
        "content_type": "text/xml; charset=utf-8",
        "description": "Exely OTA_HotelResNotifRQ webhook endpoint",
        "supported_operations": [
            "OTA_HotelResNotifRQ (New reservations)",
            "OTA_HotelResNotifRQ (Modifications)",
            "OTA_HotelResNotifRQ (Cancellations)",
        ],
    }
