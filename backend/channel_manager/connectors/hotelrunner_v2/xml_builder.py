"""
HotelRunner XML Builder - Constructs OTA-standard XML requests.

Supported message types:
  - OTA_HotelAvailNotifRQ (inventory push)
  - OTA_HotelRateAmountNotifRQ (rate push)
  - OTA_ReadRQ (reservation pull)
  - OTA_NotifReportRQ (acknowledgement)
"""

from datetime import UTC, datetime
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring


def _xml_header(message_type: str, hr_id: str, timestamp: str | None = None) -> Element:
    """Create root OTA element with standard attributes."""
    ts = timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    root = Element(message_type)
    root.set("xmlns", "http://www.opentravel.org/OTA/2003/05")
    root.set("TimeStamp", ts)
    root.set("Version", "1.0")
    root.set("Target", "Production")
    pos = SubElement(root, "POS")
    source = SubElement(pos, "Source")
    booking_channel = SubElement(source, "BookingChannel")
    booking_channel.set("Type", "7")
    company_name = SubElement(booking_channel, "CompanyName")
    company_name.set("Code", hr_id)
    company_name.text = "SyrocePMS"
    return root


def build_availability_notif(
    hr_id: str,
    updates: list[dict[str, Any]],
) -> str:
    """
    Build OTA_HotelAvailNotifRQ XML for inventory updates.

    Each update dict:
      {
        "room_type_code": str,
        "date_start": "YYYY-MM-DD",
        "date_end": "YYYY-MM-DD",
        "available": int,
        "restriction_status": "Open" | "Close",
      }
    """
    root = _xml_header("OTA_HotelAvailNotifRQ", hr_id)
    avail_status_messages = SubElement(root, "AvailStatusMessages")
    avail_status_messages.set("HotelCode", hr_id)

    for u in updates:
        msg = SubElement(avail_status_messages, "AvailStatusMessage")
        msg.set("BookingLimit", str(u.get("available", 0)))

        status_app = SubElement(msg, "StatusApplicationControl")
        status_app.set("Start", u["date_start"])
        status_app.set("End", u["date_end"])
        status_app.set("InvTypeCode", u["room_type_code"])

        if u.get("rate_plan_code"):
            status_app.set("RatePlanCode", u["rate_plan_code"])

        restriction = u.get("restriction_status", "Open")
        if restriction == "Close":
            status_app.set("RestrictionStatus", "Close")

        # Restriction overrides
        lengths = SubElement(msg, "LengthsOfStay")
        if u.get("min_stay"):
            los = SubElement(lengths, "LengthOfStay")
            los.set("MinMaxMessageType", "SetMinLOS")
            los.set("Time", str(u["min_stay"]))
            los.set("TimeUnit", "Day")
        if u.get("max_stay"):
            los = SubElement(lengths, "LengthOfStay")
            los.set("MinMaxMessageType", "SetMaxLOS")
            los.set("Time", str(u["max_stay"]))
            los.set("TimeUnit", "Day")

    return tostring(root, encoding="unicode", xml_declaration=True)


def build_rate_amount_notif(
    hr_id: str,
    updates: list[dict[str, Any]],
) -> str:
    """
    Build OTA_HotelRateAmountNotifRQ XML for rate updates.

    Each update dict:
      {
        "room_type_code": str,
        "rate_plan_code": str,
        "date_start": "YYYY-MM-DD",
        "date_end": "YYYY-MM-DD",
        "amount_after_tax": float,
        "currency": str,
        "occupancy_rates": [{"adults": int, "amount": float}],
      }
    """
    root = _xml_header("OTA_HotelRateAmountNotifRQ", hr_id)
    rate_amount_messages = SubElement(root, "RateAmountMessages")
    rate_amount_messages.set("HotelCode", hr_id)

    for u in updates:
        msg = SubElement(rate_amount_messages, "RateAmountMessage")

        status_app = SubElement(msg, "StatusApplicationControl")
        status_app.set("Start", u["date_start"])
        status_app.set("End", u["date_end"])
        status_app.set("InvTypeCode", u["room_type_code"])
        status_app.set("RatePlanCode", u["rate_plan_code"])

        rates = SubElement(msg, "Rates")
        rate = SubElement(rates, "Rate")

        base_by_guests = SubElement(rate, "BaseByGuestAmts")
        if u.get("occupancy_rates"):
            for occ in u["occupancy_rates"]:
                bg = SubElement(base_by_guests, "BaseByGuestAmt")
                bg.set("NumberOfGuests", str(occ["adults"]))
                bg.set("AmountAfterTax", f"{occ['amount']:.2f}")
                bg.set("CurrencyCode", u.get("currency", "TRY"))
        else:
            bg = SubElement(base_by_guests, "BaseByGuestAmt")
            bg.set("AmountAfterTax", f"{u.get('amount_after_tax', 0):.2f}")
            bg.set("CurrencyCode", u.get("currency", "TRY"))

    return tostring(root, encoding="unicode", xml_declaration=True)


def build_read_rq(
    hr_id: str,
    read_type: str = "reservations",
    date_start: str | None = None,
    date_end: str | None = None,
) -> str:
    """
    Build OTA_ReadRQ XML for pulling reservations.
    """
    root = _xml_header("OTA_ReadRQ", hr_id)
    read_requests = SubElement(root, "ReadRequests")
    hotel_read = SubElement(read_requests, "HotelReadRequest")
    hotel_read.set("HotelCode", hr_id)

    if date_start:
        selection = SubElement(hotel_read, "SelectionCriteria")
        selection.set("Start", date_start)
        if date_end:
            selection.set("End", date_end)
        selection.set("SelectionType", "Undelivered")

    return tostring(root, encoding="unicode", xml_declaration=True)


def build_notif_report_rq(
    hr_id: str,
    reservation_ids: list[str],
) -> str:
    """
    Build OTA_NotifReportRQ XML for acknowledging received reservations.
    """
    root = _xml_header("OTA_NotifReportRQ", hr_id)
    notif_report = SubElement(root, "NotifDetails")

    for res_id in reservation_ids:
        hotel_notif = SubElement(notif_report, "HotelNotifReport")
        hotel_notif.set("HotelCode", hr_id)
        reservations = SubElement(hotel_notif, "HotelReservations")
        hotel_res = SubElement(reservations, "HotelReservation")
        hotel_res.set("ResStatus", "Commit")
        unique_id = SubElement(hotel_res, "UniqueID")
        unique_id.set("Type", "14")
        unique_id.set("ID", res_id)

    return tostring(root, encoding="unicode", xml_declaration=True)
