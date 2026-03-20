"""
Exely SOAP XML Builder
Constructs OTA-standard SOAP envelopes for the Exely/HopenAPI PMSConnect WCF service.

Security: Simple attribute-based Security header per WSDL schema:
  <Security xmlns="https://www.hopenapi.com/Api/PMSConnect" Username="..." Password="..." />

Supported messages:
  - OTA_ReadRQ              (pull reservations)
  - OTA_HotelAvailRQ        (discover rooms/rates)
  - OTA_HotelAvailNotifRQ   (ARI push — availability/restrictions)
  - OTA_HotelRateAmountNotifRQ (ARI push — rates)
  - OTA_NotifReportRQ        (delivery confirmation)
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from lxml import etree

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
OTA_NS = "http://www.opentravel.org/OTA/2003/05"
SEC_NS = "https://www.hopenapi.com/Api/PMSConnect"

# SOAPAction URIs from WSDL
SOAP_ACTIONS = {
    "OTA_HotelAvailRQ": "https://www.hopenapi.com/Api/PMSConnect/HotelAvailRQ",
    "OTA_ReadRQ": "https://www.hopenapi.com/Api/PMSConnect/HotelReadReservationRQ",
    "OTA_HotelAvailNotifRQ": "https://www.hopenapi.com/Api/PMSConnect/HotelAvailNotifRQ",
    "OTA_HotelRateAmountNotifRQ": "https://www.hopenapi.com/Api/PMSConnect/HotelRateAmountNotifRQ",
    "OTA_NotifReportRQ": "https://www.hopenapi.com/Api/PMSConnect/NotifReportRQRequest",
    "OTA_HotelInvCountNotifRQ": "https://www.hopenapi.com/Api/PMSConnect/HotelInvCountNotifRQRequest",
    "OTA_HotelResNotifRQ": "https://www.hopenapi.com/Api/PMSConnect/HotelResNotifRQRequest",
    "PingRQ": "https://www.hopenapi.com/Api/PMSConnect/PingRQRequest",
}


def get_soap_action_uri(operation: str) -> str:
    """Resolve an OTA operation name to its full WSDL SOAPAction URI."""
    return SOAP_ACTIONS.get(operation, operation)


def _soap_envelope(username: str, password: str, hotel_code: str, body_element: etree._Element) -> str:
    """Wrap an OTA body element in a SOAP envelope with the PMSConnect Security header."""
    env = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"s": SOAP_NS})

    # Header — simple Security element per WSDL xsd1
    header = etree.SubElement(env, f"{{{SOAP_NS}}}Header")
    etree.SubElement(header, f"{{{SEC_NS}}}Security", attrib={
        "Username": username,
        "Password": password,
    })

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
        # Exely requires SelectionCriteria even for specific reservation lookups
        etree.SubElement(read_request, f"{{{OTA_NS}}}SelectionCriteria", attrib={
            "SelectionType": "All",
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
    create_datetime: str = None, last_modify_datetime: str = None,
    res_status: str = "Book",
) -> str:
    """Build OTA_NotifReportRQ to confirm reservation delivery.
    
    res_status values:
      - "Book"   → new reservation confirmed  (CreateDateTime mandatory)
      - "Modify" → modification confirmed      (LastModifyDateTime mandatory)
      - "Cancel" → cancellation confirmed       (LastModifyDateTime mandatory)
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rq = etree.Element(f"{{{OTA_NS}}}OTA_NotifReportRQ", attrib={
        "Version": "1.0",
        "TimeStamp": now_str,
    })

    etree.SubElement(rq, f"{{{OTA_NS}}}Success")

    notif_report = etree.SubElement(rq, f"{{{OTA_NS}}}NotifDetails", attrib={
        "HotelCode": hotel_code,
    })
    hotel_notif = etree.SubElement(notif_report, f"{{{OTA_NS}}}HotelNotifReport", attrib={
        "HotelCode": hotel_code,
    })

    notif_item = etree.SubElement(hotel_notif, f"{{{OTA_NS}}}HotelReservations")

    # Build attributes based on res_status type
    res_attrib = {"ResStatus": res_status}
    # Exely requires both CreateDateTime and LastModifyDateTime regardless of res_status
    res_attrib["CreateDateTime"] = create_datetime or now_str
    res_attrib["LastModifyDateTime"] = last_modify_datetime or create_datetime or now_str

    hotel_res = etree.SubElement(notif_item, f"{{{OTA_NS}}}HotelReservation", attrib=res_attrib)

    etree.SubElement(hotel_res, f"{{{OTA_NS}}}UniqueID", attrib={
        "Type": "14",
        "ID": reservation_id,
    })

    res_id = etree.SubElement(hotel_res, f"{{{OTA_NS}}}ResGlobalInfo")
    hotel_res_ids = etree.SubElement(res_id, f"{{{OTA_NS}}}HotelReservationIDs")
    etree.SubElement(hotel_res_ids, f"{{{OTA_NS}}}HotelReservationID", attrib={
        "ResID_Type": "14",
        "ResID_Value": reservation_id,
    })
    etree.SubElement(hotel_res_ids, f"{{{OTA_NS}}}HotelReservationID", attrib={
        "ResID_Type": "14",
        "ResID_Value": confirmation_number,
        "ResID_Source": "PMS",
    })

    return _soap_envelope(username, password, hotel_code, rq)


def build_hotel_res_notif_rq(
    username: str, password: str, hotel_code: str,
    reservation_id: str, confirmation_number: str,
    create_datetime: str = None, last_modify_datetime: str = None,
    res_status: str = "Reserved",
) -> str:
    """Build OTA_HotelResNotifRQ to push reservation confirmation back to Exely."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rq = etree.Element(f"{{{OTA_NS}}}OTA_HotelResNotifRQ", attrib={
        "Version": "1.0",
        "TimeStamp": now_str,
    })

    reservations = etree.SubElement(rq, f"{{{OTA_NS}}}HotelReservations")
    hotel_res = etree.SubElement(reservations, f"{{{OTA_NS}}}HotelReservation", attrib={
        "ResStatus": res_status,
        "CreateDateTime": create_datetime or now_str,
        "LastModifyDateTime": last_modify_datetime or create_datetime or now_str,
    })

    etree.SubElement(hotel_res, f"{{{OTA_NS}}}UniqueID", attrib={
        "Type": "14",
        "ID": reservation_id,
    })

    res_info = etree.SubElement(hotel_res, f"{{{OTA_NS}}}ResGlobalInfo")
    hotel_res_ids = etree.SubElement(res_info, f"{{{OTA_NS}}}HotelReservationIDs")
    etree.SubElement(hotel_res_ids, f"{{{OTA_NS}}}HotelReservationID", attrib={
        "ResID_Type": "14",
        "ResID_Value": reservation_id,
    })
    etree.SubElement(hotel_res_ids, f"{{{OTA_NS}}}HotelReservationID", attrib={
        "ResID_Type": "14",
        "ResID_Value": confirmation_number,
        "ResID_Source": "PMS",
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
    """Build OTA_HotelAvailNotifRQ for availability + restrictions only.
    Rate updates go via OTA_HotelRateAmountNotifRQ separately."""
    rq = etree.Element(f"{{{OTA_NS}}}OTA_HotelAvailNotifRQ", attrib={
        "Version": "1.0",
        "TimeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    avail_status = etree.SubElement(rq, f"{{{OTA_NS}}}AvailStatusMessages", attrib={
        "HotelCode": hotel_code,
    })

    msg = etree.SubElement(avail_status, f"{{{OTA_NS}}}AvailStatusMessage")

    status_ctrl_attrib = {
        "Start": start_date,
        "End": end_date,
        "InvTypeCode": room_type_code,
        "RatePlanCode": rate_plan_code,
    }
    etree.SubElement(msg, f"{{{OTA_NS}}}StatusApplicationControl", attrib=status_ctrl_attrib)

    if availability is not None:
        msg.set("BookingLimit", str(availability))

    if stop_sell is not None:
        etree.SubElement(msg, f"{{{OTA_NS}}}RestrictionStatus", attrib={
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


def build_rate_amount_notif_rq(
    username: str, password: str, hotel_code: str,
    room_type_code: str, rate_plan_code: str,
    start_date: str, end_date: str,
    rate_amount: float,
    currency: str = "TRY",
) -> str:
    """Build OTA_HotelRateAmountNotifRQ for rate-only push."""
    rq = etree.Element(f"{{{OTA_NS}}}OTA_HotelRateAmountNotifRQ", attrib={
        "Version": "1.0",
        "TimeStamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    rate_amount_msgs = etree.SubElement(rq, f"{{{OTA_NS}}}RateAmountMessages", attrib={
        "HotelCode": hotel_code,
    })

    msg = etree.SubElement(rate_amount_msgs, f"{{{OTA_NS}}}RateAmountMessage")

    etree.SubElement(msg, f"{{{OTA_NS}}}StatusApplicationControl", attrib={
        "Start": start_date,
        "End": end_date,
        "InvTypeCode": room_type_code,
        "RatePlanCode": rate_plan_code,
    })

    rates = etree.SubElement(msg, f"{{{OTA_NS}}}Rates")
    rate_el = etree.SubElement(rates, f"{{{OTA_NS}}}Rate", attrib={
        "Start": start_date,
        "End": end_date,
    })
    base_by_guest = etree.SubElement(rate_el, f"{{{OTA_NS}}}BaseByGuestAmts")
    etree.SubElement(base_by_guest, f"{{{OTA_NS}}}BaseByGuestAmt", attrib={
        "AmountAfterTax": f"{rate_amount:.2f}",
        "CurrencyCode": currency,
    })

    return _soap_envelope(username, password, hotel_code, rq)
