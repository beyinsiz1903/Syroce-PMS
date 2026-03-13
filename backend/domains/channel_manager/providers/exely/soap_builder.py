"""
Exely SOAP XML Builder
Constructs OTA-standard SOAP envelopes with WSSE Security headers.

Security: WSSE UsernameToken with Timestamp (wsu:Created, wsu:Expires) + Nonce.

Supported messages:
  - OTA_ReadRQ       (pull reservations)
  - OTA_HotelAvailRQ (discover rooms/rates)
  - OTA_NotifReportRQ(ARI push)
"""
import base64
import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from lxml import etree

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
OTA_NS = "http://www.opentravel.org/OTA/2003/05"

NSMAP_SOAP = {"soapenv": SOAP_NS, "wsse": WSSE_NS, "wsu": WSU_NS, "ota": OTA_NS}


def _soap_envelope(username: str, password: str, hotel_code: str, body_element: etree._Element) -> str:
    """Wrap an OTA body element in a full SOAP envelope with WSSE auth + Timestamp + Nonce."""
    env = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap=NSMAP_SOAP)

    # Header with WSSE Security
    header = etree.SubElement(env, f"{{{SOAP_NS}}}Header")
    security = etree.SubElement(header, f"{{{WSSE_NS}}}Security", attrib={
        f"{{{SOAP_NS}}}mustUnderstand": "1",
    })

    # wsu:Timestamp — Created + Expires (5 min TTL)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=5)
    timestamp = etree.SubElement(security, f"{{{WSU_NS}}}Timestamp")
    created_el = etree.SubElement(timestamp, f"{{{WSU_NS}}}Created")
    created_el.text = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_el = etree.SubElement(timestamp, f"{{{WSU_NS}}}Expires")
    expires_el.text = expires.strftime("%Y-%m-%dT%H:%M:%SZ")

    # UsernameToken with Nonce
    username_token = etree.SubElement(security, f"{{{WSSE_NS}}}UsernameToken")
    un_el = etree.SubElement(username_token, f"{{{WSSE_NS}}}Username")
    un_el.text = username
    pw_el = etree.SubElement(username_token, f"{{{WSSE_NS}}}Password", attrib={
        "Type": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText",
    })
    pw_el.text = password

    # Nonce (16 random bytes, base64-encoded) — replay attack protection
    nonce_bytes = os.urandom(16)
    nonce_el = etree.SubElement(username_token, f"{{{WSSE_NS}}}Nonce", attrib={
        "EncodingType": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary",
    })
    nonce_el.text = base64.b64encode(nonce_bytes).decode("ascii")

    # wsu:Created inside UsernameToken
    token_created = etree.SubElement(username_token, f"{{{WSU_NS}}}Created")
    token_created.text = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # HotelCode in security context
    hotel_el = etree.SubElement(security, "HotelCode")
    hotel_el.text = hotel_code

    # Body
    body = etree.SubElement(env, f"{{{SOAP_NS}}}Body")
    body.append(body_element)

    return etree.tostring(env, xml_declaration=True, encoding="UTF-8", pretty_print=True).decode("utf-8")


def build_read_rq(
    username: str, password: str, hotel_code: str,
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    reservation_id: Optional[str] = None,
) -> str:
    """
    Build OTA_ReadRQ to pull reservations.
    If reservation_id is provided, fetches a specific reservation.
    Otherwise fetches reservations in [from_date, to_date] range.
    """
    rq = etree.Element(f"{{{OTA_NS}}}OTA_ReadRQ", attrib={
        "Version": "1.0",
        "TimeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    read_requests = etree.SubElement(rq, f"{{{OTA_NS}}}ReadRequests")
    read_request = etree.SubElement(read_requests, f"{{{OTA_NS}}}HotelReadRequest", attrib={
        "HotelCode": hotel_code,
    })

    if reservation_id:
        etree.SubElement(read_request, f"{{{OTA_NS}}}UniqueID", attrib={
            "Type": "14",
            "ID": reservation_id,
        })
    else:
        selection = etree.SubElement(read_request, f"{{{OTA_NS}}}SelectionCriteria", attrib={
            "SelectionType": "Undelivered",
        })
        if from_date:
            selection.set("Start", from_date)
        if to_date:
            selection.set("End", to_date)

    return _soap_envelope(username, password, hotel_code, rq)


def build_hotel_avail_rq(
    username: str, password: str, hotel_code: str,
    checkin: str, checkout: str,
) -> str:
    """Build OTA_HotelAvailRQ to discover rooms and rates."""
    rq = etree.Element(f"{{{OTA_NS}}}OTA_HotelAvailRQ", attrib={
        "Version": "1.0",
        "TimeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    avail_request = etree.SubElement(rq, f"{{{OTA_NS}}}AvailRequestSegments")
    segment = etree.SubElement(avail_request, f"{{{OTA_NS}}}AvailRequestSegment")

    etree.SubElement(segment, f"{{{OTA_NS}}}StayDateRange", attrib={
        "Start": checkin,
        "End": checkout,
    })

    hotel_criteria = etree.SubElement(segment, f"{{{OTA_NS}}}HotelSearchCriteria")
    criterion = etree.SubElement(hotel_criteria, f"{{{OTA_NS}}}Criterion")
    etree.SubElement(criterion, f"{{{OTA_NS}}}HotelRef", attrib={
        "HotelCode": hotel_code,
    })

    return _soap_envelope(username, password, hotel_code, rq)


def build_notif_report_rq(
    username: str, password: str, hotel_code: str,
    reservation_id: str, confirmation_number: str,
) -> str:
    """Build OTA_NotifReportRQ to confirm reservation delivery."""
    rq = etree.Element(f"{{{OTA_NS}}}OTA_NotifReportRQ", attrib={
        "Version": "1.0",
        "TimeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    notif_report = etree.SubElement(rq, f"{{{OTA_NS}}}NotifDetails")
    hotel_notif = etree.SubElement(notif_report, f"{{{OTA_NS}}}HotelNotifReport", attrib={
        "HotelCode": hotel_code,
    })

    notif_item = etree.SubElement(hotel_notif, f"{{{OTA_NS}}}HotelReservations")
    hotel_res = etree.SubElement(notif_item, f"{{{OTA_NS}}}HotelReservation")

    unique_id = etree.SubElement(hotel_res, f"{{{OTA_NS}}}UniqueID", attrib={  # noqa: F841
        "Type": "14",
        "ID": reservation_id,
    })
    res_id = etree.SubElement(hotel_res, f"{{{OTA_NS}}}ResGlobalInfo")
    hotel_res_ids = etree.SubElement(res_id, f"{{{OTA_NS}}}HotelReservationIDs")
    etree.SubElement(hotel_res_ids, f"{{{OTA_NS}}}HotelReservationID", attrib={
        "ResID_Type": "14",
        "ResID_Value": confirmation_number,
    })

    return _soap_envelope(username, password, hotel_code, rq)


def build_ari_update_rq(
    username: str, password: str, hotel_code: str,
    room_type_code: str, rate_plan_code: str,
    start_date: str, end_date: str,
    availability: Optional[int] = None,
    rate_amount: Optional[float] = None,
    currency: str = "TRY",
    stop_sell: Optional[bool] = None,
    min_stay: Optional[int] = None,
) -> str:
    """Build OTA_HotelAvailNotifRQ for ARI delta push."""
    rq = etree.Element(f"{{{OTA_NS}}}OTA_HotelAvailNotifRQ", attrib={
        "Version": "1.0",
        "TimeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    avail_status = etree.SubElement(rq, f"{{{OTA_NS}}}AvailStatusMessages", attrib={
        "HotelCode": hotel_code,
    })

    msg = etree.SubElement(avail_status, f"{{{OTA_NS}}}AvailStatusMessage")

    status_app = etree.SubElement(msg, f"{{{OTA_NS}}}StatusApplicationControl", attrib={  # noqa: F841
        "Start": start_date,
        "End": end_date,
        "InvTypeCode": room_type_code,
        "RatePlanCode": rate_plan_code,
    })

    if availability is not None:
        lengths = etree.SubElement(msg, f"{{{OTA_NS}}}LengthsOfStay")  # noqa: F841
        etree.SubElement(msg, f"{{{OTA_NS}}}BookingLimit").text = str(availability)

    if rate_amount is not None:
        rates = etree.SubElement(msg, f"{{{OTA_NS}}}Rates")
        rate_el = etree.SubElement(rates, f"{{{OTA_NS}}}Rate")
        base_by_guest = etree.SubElement(rate_el, f"{{{OTA_NS}}}BaseByGuestAmts")
        etree.SubElement(base_by_guest, f"{{{OTA_NS}}}BaseByGuestAmt", attrib={
            "AmountAfterTax": f"{rate_amount:.2f}",
            "CurrencyCode": currency,
        })

    if stop_sell is not None:
        restriction = etree.SubElement(msg, f"{{{OTA_NS}}}RestrictionStatus", attrib={  # noqa: F841
            "Status": "Close" if stop_sell else "Open",
            "Restriction": "Arrival",
        })

    if min_stay is not None:
        los = etree.SubElement(msg, f"{{{OTA_NS}}}LengthsOfStay")
        etree.SubElement(los, f"{{{OTA_NS}}}LengthOfStay", attrib={
            "Time": str(min_stay),
            "MinMaxMessageType": "SetMinLOS",
        })

    return _soap_envelope(username, password, hotel_code, rq)
