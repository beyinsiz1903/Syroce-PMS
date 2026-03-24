"""
Exely SOAP Response Parser
Parses OTA-standard XML responses from the Exely channel manager.
"""
import logging
from typing import Any, Dict, Optional

from defusedxml import ElementTree as safe_ET

logger = logging.getLogger(__name__)

OTA_NS = "http://www.opentravel.org/OTA/2003/05"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


def _ns(tag: str, ns: str = OTA_NS) -> str:
    return f"{{{ns}}}{tag}"


def _text(el, default=""):
    return el.text.strip() if el is not None and el.text else default


def _attr(el, key, default=""):
    return el.get(key, default) if el is not None else default


def parse_soap_response(xml_bytes: bytes) -> Dict[str, Any]:
    """Parse a SOAP envelope, extract body, detect faults."""
    try:
        root = safe_ET.fromstring(xml_bytes)
    except Exception as e:
        return {"success": False, "error": f"XML parse error: {e}", "body": None}

    # Check for SOAP Fault
    fault = root.find(f".//{_ns('Fault', SOAP_NS)}")
    if fault is not None:
        faultstring = _text(fault.find("faultstring"))
        faultcode = _text(fault.find("faultcode"))
        return {"success": False, "error": f"SOAP Fault [{faultcode}]: {faultstring}", "body": None}

    # Extract Body content
    body = root.find(f"{_ns('Body', SOAP_NS)}")
    if body is None:
        return {"success": False, "error": "No SOAP Body found", "body": None}

    # Get first child of body (the actual response)
    children = list(body)
    if not children:
        return {"success": False, "error": "Empty SOAP Body", "body": None}

    return {"success": True, "error": None, "body": children[0]}


def parse_read_rs(xml_bytes: bytes) -> Dict[str, Any]:
    """Parse OTA_ReadRS / OTA_ResRetrieveRS to extract reservations."""
    envelope = parse_soap_response(xml_bytes)
    if not envelope["success"]:
        return envelope

    body = envelope["body"]

    # Check for OTA-level Errors (not SOAP Fault, but OTA Error elements)
    errors_el = body.find(_ns("Errors"))
    if errors_el is not None:
        error_msgs = []
        for err in errors_el.findall(_ns("Error")):
            code = _attr(err, "Code", "")
            msg = _text(err, "Unknown error")
            error_msgs.append(f"OTA Error [{code}]: {msg}")
        if error_msgs:
            logger.warning("OTA_ReadRS returned errors: %s", "; ".join(error_msgs))
            return {"success": False, "error": "; ".join(error_msgs), "reservations": [], "count": 0}

    reservations = []

    # Look for HotelReservation elements
    for hr in body.iter(_ns("HotelReservation")):
        res = _parse_hotel_reservation(hr)
        if res:
            reservations.append(res)

    return {"success": True, "reservations": reservations, "count": len(reservations)}


def _parse_hotel_reservation(hr_el) -> Optional[Dict[str, Any]]:
    """Parse a single HotelReservation element to a dict."""
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

        # Room type
        for rt in room_stay.iter(_ns("RoomType")):
            room["room_type_code"] = _attr(rt, "RoomTypeCode")
            room["room_name"] = _attr(rt, "RoomDescription", _attr(rt, "RoomTypeCode"))

        # Rate plan
        for rp in room_stay.iter(_ns("RatePlan")):
            room["rate_plan_code"] = _attr(rp, "RatePlanCode")
            room["rate_plan_name"] = _attr(rp, "RatePlanName", "")

        # Room rates
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

        # Guest counts
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

        # Total
        for total_el in room_stay.iter(_ns("Total")):
            room["amount"] = _safe_float(_attr(total_el, "AmountAfterTax", "0"))
            room["currency"] = _attr(total_el, "CurrencyCode", "TRY")

        # Time span
        for ts in room_stay.iter(_ns("TimeSpan")):
            room["check_in"] = _attr(ts, "Start", "")
            room["check_out"] = _attr(ts, "End", "")

        if room.get("room_type_code"):
            rooms.append(room)

    res["rooms"] = rooms

    # Dates from first room or global
    if rooms:
        res["checkin_date"] = rooms[0].get("check_in", "")
        res["checkout_date"] = rooms[0].get("check_out", "")
        res["currency"] = rooms[0].get("currency", "TRY")

    # Global info
    global_info = hr_el.find(f".//{_ns('ResGlobalInfo')}")
    if global_info is not None:
        total_el = global_info.find(_ns("Total"))
        if total_el is not None:
            res["total"] = _safe_float(_attr(total_el, "AmountAfterTax", "0"))
            res["currency"] = _attr(total_el, "CurrencyCode", res.get("currency", "TRY"))

        # Special requests / comments
        for comment in global_info.iter(_ns("Comment")):
            text_el = comment.find(_ns("Text"))
            res["notes"] = _text(text_el)

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


def parse_hotel_avail_rs(xml_bytes: bytes) -> Dict[str, Any]:
    """Parse OTA_HotelAvailRS to extract room types and rate plans."""
    envelope = parse_soap_response(xml_bytes)
    if not envelope["success"]:
        return envelope

    body = envelope["body"]
    room_types = []
    rate_plans = []

    for room_stay in body.iter(_ns("RoomStay")):
        for rt in room_stay.iter(_ns("RoomType")):
            # HopenAPI uses RoomDescription with Name attribute
            desc = rt.find(_ns("RoomDescription"))
            name = _attr(desc, "Name", _attr(rt, "RoomDescription", _attr(rt, "RoomTypeCode")))
            room_types.append({
                "code": _attr(rt, "RoomTypeCode"),
                "name": name,
                "quantity": int(_attr(rt, "NumberOfUnits", "0")),
            })
        for rp in room_stay.iter(_ns("RatePlan")):
            desc = rp.find(_ns("RatePlanDescription"))
            name = _attr(desc, "Name", _attr(rp, "RatePlanName", ""))
            rate_plans.append({
                "code": _attr(rp, "RatePlanCode"),
                "name": name,
            })

    # Deduplicate
    seen_rooms = set()
    unique_rooms = []
    for r in room_types:
        if r["code"] not in seen_rooms:
            seen_rooms.add(r["code"])
            unique_rooms.append(r)

    seen_rates = set()
    unique_rates = []
    for r in rate_plans:
        if r["code"] not in seen_rates:
            seen_rates.add(r["code"])
            unique_rates.append(r)

    return {"success": True, "room_types": unique_rooms, "rate_plans": unique_rates}


def parse_notif_report_rs(xml_bytes: bytes) -> Dict[str, Any]:
    """Parse OTA_NotifReportRS for delivery confirmation."""
    envelope = parse_soap_response(xml_bytes)
    if not envelope["success"]:
        return envelope

    body = envelope["body"]

    # Check for success/errors
    errors_el = body.find(f".//{_ns('Errors')}")
    if errors_el is not None:
        msgs = []
        for err in errors_el.iter(_ns("Error")):
            msgs.append(_text(err) or _attr(err, "ShortText"))
        return {"success": False, "error": "; ".join(msgs)}

    return {"success": True, "message": "Delivery confirmed"}


def parse_ari_update_rs(xml_bytes: bytes) -> Dict[str, Any]:
    """Parse ARI update response."""
    envelope = parse_soap_response(xml_bytes)
    if not envelope["success"]:
        return envelope

    body = envelope["body"]
    errors_el = body.find(f".//{_ns('Errors')}")
    if errors_el is not None:
        msgs = []
        for err in errors_el.iter(_ns("Error")):
            msgs.append(_text(err) or _attr(err, "ShortText"))
        return {"success": False, "error": "; ".join(msgs)}

    return {"success": True, "message": "ARI update applied"}


def _safe_float(val) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
