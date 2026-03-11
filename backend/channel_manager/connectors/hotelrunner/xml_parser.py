"""
HotelRunner XML Parser - Parses OTA-standard XML responses from HotelRunner.
Converts raw XML into structured Python dicts and canonical models.
"""
import logging
from typing import Dict, Any, List, Optional
from xml.etree import ElementTree as ET

from .errors import XmlParseError

logger = logging.getLogger("channel_manager.hotelrunner.xml_parser")

NS = {"ota": "http://www.opentravel.org/OTA/2003/05"}


def _find_text(elem: ET.Element, path: str, default: str = "") -> str:
    """Safe text extraction from XML element."""
    child = elem.find(path, NS)
    if child is not None and child.text:
        return child.text.strip()
    return default


def _find_attr(elem: ET.Element, path: str, attr: str, default: str = "") -> str:
    """Safe attribute extraction from XML element at given path."""
    child = elem.find(path, NS)
    if child is not None:
        return child.get(attr, default)
    return default


def parse_response_status(xml_str: str) -> Dict[str, Any]:
    """Parse generic OTA response for success/error status."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise XmlParseError(f"Invalid XML: {e}", raw_xml=xml_str)

    # Check for errors
    errors_elem = root.find(".//Errors") or root.find(".//ota:Errors", NS)
    if errors_elem is not None:
        error_list = []
        for err in errors_elem.findall("Error") + errors_elem.findall("ota:Error", NS):
            error_list.append({
                "code": err.get("Code", ""),
                "type": err.get("Type", ""),
                "message": err.text.strip() if err.text else err.get("ShortText", ""),
            })
        return {"success": False, "errors": error_list}

    # Check for warnings
    warnings = []
    warnings_elem = root.find(".//Warnings") or root.find(".//ota:Warnings", NS)
    if warnings_elem is not None:
        for w in warnings_elem.findall("Warning") + warnings_elem.findall("ota:Warning", NS):
            warnings.append(w.text.strip() if w.text else w.get("ShortText", ""))

    return {"success": True, "errors": [], "warnings": warnings}


def parse_reservations_response(xml_str: str) -> List[Dict[str, Any]]:
    """
    Parse OTA_ResRetrieveRS or HotelRunner reservation response.
    Returns a list of raw reservation dicts ready for canonical mapping.
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise XmlParseError(f"Invalid reservation XML: {e}", raw_xml=xml_str)

    reservations = []

    # HotelRunner returns reservations in HotelReservations/HotelReservation
    for hotel_res in (
        root.findall(".//HotelReservation") +
        root.findall(".//ota:HotelReservation", NS)
    ):
        res = _parse_single_reservation(hotel_res)
        if res:
            reservations.append(res)

    return reservations


def _parse_single_reservation(elem: ET.Element) -> Optional[Dict[str, Any]]:
    """Parse a single HotelReservation element into a structured dict."""
    res_status = elem.get("ResStatus", "Commit")

    # UniqueID (external confirmation number)
    unique_ids = {}
    for uid in elem.findall("UniqueID") + elem.findall("ota:UniqueID", NS):
        uid_type = uid.get("Type", "")
        uid_id = uid.get("ID", "")
        unique_ids[uid_type] = uid_id

    external_id = unique_ids.get("14", unique_ids.get("16", ""))
    confirmation_number = unique_ids.get("14", "")

    # Guest details
    guest = {}
    res_guests = elem.find("ResGuests") or elem.find("ota:ResGuests", NS)
    if res_guests is not None:
        guest_elem = res_guests.find(".//Customer") or res_guests.find(".//ota:Customer", NS)
        if guest_elem is not None:
            name_elem = guest_elem.find("PersonName") or guest_elem.find("ota:PersonName", NS)
            if name_elem is not None:
                guest["first_name"] = _find_text(name_elem, "GivenName") or _find_text(name_elem, "ota:GivenName")
                guest["last_name"] = _find_text(name_elem, "Surname") or _find_text(name_elem, "ota:Surname")
            guest["email"] = _find_text(guest_elem, ".//Email") or _find_text(guest_elem, ".//ota:Email")
            guest["phone"] = _find_text(guest_elem, ".//Telephone") or _find_text(guest_elem, ".//ota:Telephone")

    # Room stay details
    room_stays = elem.find("RoomStays") or elem.find("ota:RoomStays", NS)
    rooms = []
    total_amount = 0.0
    currency = "TRY"
    arrival = ""
    departure = ""
    room_type_code = ""
    rate_plan_code = ""
    meal_plan = ""

    if room_stays is not None:
        for rs in room_stays.findall("RoomStay") + room_stays.findall("ota:RoomStay", NS):
            # Room type
            for rt in rs.findall(".//RoomType") + rs.findall(".//ota:RoomType", NS):
                room_type_code = rt.get("RoomTypeCode", "")

            # Rate plan
            for rp in rs.findall(".//RatePlan") + rs.findall(".//ota:RatePlan", NS):
                rate_plan_code = rp.get("RatePlanCode", "")
                meal_plan = rp.get("MealPlanCode", "")

            # Time span
            ts = rs.find("TimeSpan") or rs.find("ota:TimeSpan", NS)
            if ts is not None:
                arrival = ts.get("Start", "")
                departure = ts.get("End", "")

            # Total
            total_elem = rs.find(".//Total") or rs.find(".//ota:Total", NS)
            if total_elem is not None:
                try:
                    total_amount = float(total_elem.get("AmountAfterTax", "0"))
                except (ValueError, TypeError):
                    total_amount = 0.0
                currency = total_elem.get("CurrencyCode", "TRY")

            # Guest counts
            adult_count = 0
            child_count = 0
            for gc in rs.findall(".//GuestCount") + rs.findall(".//ota:GuestCount", NS):
                age_code = gc.get("AgeQualifyingCode", "10")
                count = int(gc.get("Count", "0"))
                if age_code == "10":
                    adult_count += count
                elif age_code == "8":
                    child_count += count

            rooms.append({
                "room_type_code": room_type_code,
                "rate_plan_code": rate_plan_code,
                "adult_count": adult_count or 1,
                "child_count": child_count,
            })

    # Special requests
    special_requests = ""
    for sr in elem.findall(".//SpecialRequest") + elem.findall(".//ota:SpecialRequest", NS):
        if sr.text:
            special_requests += sr.text.strip() + "; "

    # Payment
    payment_type = ""
    guarantee = elem.find(".//Guarantee") or elem.find(".//ota:Guarantee", NS)
    if guarantee is not None:
        payment_type = guarantee.get("GuaranteeType", "")

    return {
        "external_id": external_id,
        "confirmation_number": confirmation_number,
        "res_status": res_status,
        "guest": guest,
        "arrival_date": arrival,
        "departure_date": departure,
        "room_type_code": room_type_code,
        "rate_plan_code": rate_plan_code,
        "meal_plan": meal_plan,
        "adult_count": rooms[0]["adult_count"] if rooms else 1,
        "child_count": rooms[0]["child_count"] if rooms else 0,
        "total_amount": total_amount,
        "currency": currency,
        "payment_type": payment_type,
        "special_requests": special_requests.strip("; "),
        "rooms": rooms,
        "unique_ids": unique_ids,
    }
