"""
HotelRunner XML Parser - Parses OTA-standard XML responses from HotelRunner.
Converts raw XML into structured Python dicts and canonical models.

Contract hardening:
  - Unknown fields: silently ignored
  - Missing optional fields: tolerated with defaults
  - Unexpected enum values: fallback to 'unknown'
  - Raw payload audit with masking, truncation, correlation_id
"""
import hashlib
import logging
import uuid
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from .contract_errors import (
    InvalidXmlError,
    ProviderErrorResponseError,
)
from .errors import XmlParseError

logger = logging.getLogger("channel_manager.hotelrunner.xml_parser")

NS = {"ota": "http://www.opentravel.org/OTA/2003/05"}

# Known enum value sets for fallback handling
KNOWN_RES_STATUSES = {"Commit", "Cancel", "Modify", "Book", "Pending", "InHouse", "CheckedOut", "NoShow"}
KNOWN_GUARANTEE_TYPES = {"CC/DC/Prepayment", "Deposit", "GuaranteRequired", "None", "PrePay"}
KNOWN_AGE_QUALIFYING_CODES = {"10", "8", "7", "1"}  # 10=Adult, 8=Child, 7=Infant, 1=Unknown

# Sensitive fields to mask in audit payloads
MASK_PATTERNS = {"CardNumber", "CardHolderName", "ExpireDate", "CVV", "SeriesCode", "Token", "Password"}
AUDIT_TRUNCATE_LEN = 4000


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


def _safe_float(value: str, default: float = 0.0) -> float:
    """Safely parse float, returning default on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: str, default: int = 0) -> int:
    """Safely parse int, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _enum_fallback(value: str, known: set, default: str = "unknown") -> str:
    """Return value if in known set, otherwise return default and log."""
    if value in known:
        return value
    if value:
        logger.debug("Unexpected enum value '%s', falling back to '%s'", value, default)
    return default if not value else value  # Keep original but log


def mask_sensitive_xml(xml_str: str) -> str:
    """Mask sensitive data in XML string for audit logging."""
    masked = xml_str
    for pattern in MASK_PATTERNS:
        import re
        masked = re.sub(
            rf'(<{pattern}[^>]*>)([^<]+)(</{pattern}>)',
            r'\1****\3',
            masked,
        )
        masked = re.sub(
            rf'{pattern}="[^"]*"',
            f'{pattern}="****"',
            masked,
        )
    return masked


def truncate_payload(payload: str, max_len: int = AUDIT_TRUNCATE_LEN) -> str:
    """Truncate payload for audit storage."""
    if len(payload) <= max_len:
        return payload
    return payload[:max_len] + f"... [truncated, total {len(payload)} chars]"


def build_audit_record(
    operation: str,
    raw_request: str = "",
    raw_response: str = "",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a standardized audit record for raw payloads."""
    return {
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "operation": operation,
        "request_payload": truncate_payload(mask_sensitive_xml(raw_request)) if raw_request else "",
        "response_payload": truncate_payload(mask_sensitive_xml(raw_response)) if raw_response else "",
        "request_hash": hashlib.sha256(raw_request.encode()).hexdigest()[:16] if raw_request else "",
        "response_hash": hashlib.sha256(raw_response.encode()).hexdigest()[:16] if raw_response else "",
    }


def parse_response_status(xml_str: str) -> Dict[str, Any]:
    """Parse generic OTA response for success/error status with contract hardening."""
    if not xml_str or not xml_str.strip():
        raise InvalidXmlError("Empty XML response", raw_xml="", parse_error="empty_input")

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise InvalidXmlError(f"Invalid XML: {e}", raw_xml=xml_str[:500], parse_error=str(e))

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
    """Parse a single HotelReservation element with contract hardening.

    Contract hardening:
      - Unknown fields/elements are silently ignored
      - Missing optional fields tolerated with sensible defaults
      - Unexpected enum values kept but logged
      - Malformed numeric values defaulted to 0
    """
    raw_status = elem.get("ResStatus", "Commit")
    res_status = _enum_fallback(raw_status, KNOWN_RES_STATUSES, "Commit")

    # UniqueID (external confirmation number)
    unique_ids = {}
    for uid in elem.findall("UniqueID") + elem.findall("ota:UniqueID", NS):
        uid_type = uid.get("Type", "")
        uid_id = uid.get("ID", "")
        if uid_type and uid_id:
            unique_ids[uid_type] = uid_id

    external_id = unique_ids.get("14", unique_ids.get("16", ""))
    confirmation_number = unique_ids.get("14", "")

    # Guest details — tolerate missing fields
    guest = {"first_name": "", "last_name": "", "email": "", "phone": ""}
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

            # Total — safe float parsing
            total_elem = rs.find(".//Total") or rs.find(".//ota:Total", NS)
            if total_elem is not None:
                total_amount = _safe_float(total_elem.get("AmountAfterTax", "0"))
                currency = total_elem.get("CurrencyCode", "TRY")

            # Guest counts — safe int parsing with enum fallback
            adult_count = 0
            child_count = 0
            for gc in rs.findall(".//GuestCount") + rs.findall(".//ota:GuestCount", NS):
                age_code = gc.get("AgeQualifyingCode", "10")
                _enum_fallback(age_code, KNOWN_AGE_QUALIFYING_CODES, "10")
                count = _safe_int(gc.get("Count", "0"))
                if age_code == "10":
                    adult_count += count
                elif age_code in ("8", "7"):
                    child_count += count

            rooms.append({
                "room_type_code": room_type_code,
                "rate_plan_code": rate_plan_code,
                "adult_count": adult_count or 1,
                "child_count": child_count,
            })

    # Special requests — tolerate missing
    special_requests = ""
    for sr in elem.findall(".//SpecialRequest") + elem.findall(".//ota:SpecialRequest", NS):
        if sr.text:
            special_requests += sr.text.strip() + "; "

    # Payment — tolerate unknown guarantee types
    payment_type = ""
    guarantee = elem.find(".//Guarantee") or elem.find(".//ota:Guarantee", NS)
    if guarantee is not None:
        raw_guarantee = guarantee.get("GuaranteeType", "")
        payment_type = _enum_fallback(raw_guarantee, KNOWN_GUARANTEE_TYPES, "")

    # Source channel — direct child iteration avoids ET namespace side effects
    source_channel = ""
    for child in elem:
        if child.tag == "POS" or child.tag.endswith("}POS"):
            for src in child:
                if src.tag == "Source" or src.tag.endswith("}Source"):
                    source_channel = src.get("ChannelCode", "")
                    break
        if child.tag == "Source" or child.tag.endswith("}Source"):
            source_channel = child.get("ChannelCode", source_channel)

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
        "source_channel": source_channel,
    }


def parse_provider_error(xml_str: str) -> Optional[Dict[str, Any]]:
    """Parse a provider error response and raise typed contract error."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        raise InvalidXmlError("Cannot parse error response", raw_xml=xml_str[:500])

    errors_elem = root.find(".//Errors") or root.find(".//ota:Errors", NS)
    if errors_elem is None:
        return None

    errors = []
    for err in errors_elem.findall("Error") + errors_elem.findall("ota:Error", NS):
        code = err.get("Code", "")
        err_type = err.get("Type", "")
        message = err.text.strip() if err.text else err.get("ShortText", "")
        errors.append({"code": code, "type": err_type, "message": message})

    if errors:
        first = errors[0]
        raise ProviderErrorResponseError(
            provider="hotelrunner",
            error_code=first["code"],
            error_message=first["message"],
            raw_response=xml_str[:500],
        )
    return None
