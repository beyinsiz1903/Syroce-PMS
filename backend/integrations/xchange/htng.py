"""HTNG 2024B / OTA-XML serialization.

Builds compact, schema-correct XML envelopes for the canonical Syroce
Xchange messages. Uses xml.etree (stdlib, no extra deps) so output is
deterministic and easy to diff in delivery logs.

Coverage (MVP): Reservation, Posting, Inventory, Rate. Other message
types fall back to a generic <Syroce.Message> wrapper.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from .schemas import MessageType, XchangeEnvelope

OTA_NS = "http://www.opentravel.org/OTA/2003/05"
HTNG_NS = "http://htng.org/2014B"


def _utc_iso(dt: datetime | None = None) -> str:
    return (dt or datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _common_attrs(env: XchangeEnvelope) -> dict[str, str]:
    return {
        "EchoToken": env.message_id,
        "TimeStamp": _utc_iso(env.occurred_at),
        "Version": "2024.2",
    }


def _root(name: str, env: XchangeEnvelope) -> ET.Element:
    el = ET.Element(f"{{{OTA_NS}}}{name}", _common_attrs(env))
    return el


# ── Reservation ──────────────────────────────────────────────────
def _build_reservation(env: XchangeEnvelope) -> ET.Element:
    p = env.payload
    msg_action = {
        MessageType.RESERVATION_CREATE: "Commit",
        MessageType.RESERVATION_MODIFY: "Modify",
        MessageType.RESERVATION_CANCEL: "Cancel",
    }.get(env.message_type, "Commit")

    root = _root("OTA_HotelResNotifRQ", env)
    root.set("ResStatus", msg_action)

    hotel_reservations = ET.SubElement(root, f"{{{OTA_NS}}}HotelReservations")
    hr = ET.SubElement(hotel_reservations, f"{{{OTA_NS}}}HotelReservation", {"CreateDateTime": _utc_iso(), "ResStatus": p.get("status", "Reserved")})

    # Unique IDs
    unique_id = ET.SubElement(hr, f"{{{OTA_NS}}}UniqueID", {"Type": "14", "ID": p["reservation_id"], "ID_Context": "SYROCE"})
    if p.get("confirmation_number"):
        ET.SubElement(hr, f"{{{OTA_NS}}}UniqueID", {"Type": "10", "ID": p["confirmation_number"], "ID_Context": "PARTNER"})  # noqa: F841
    _ = unique_id

    # RoomStays
    rstays = ET.SubElement(hr, f"{{{OTA_NS}}}RoomStays")
    for stay in p.get("room_stays", []):
        rs = ET.SubElement(rstays, f"{{{OTA_NS}}}RoomStay")
        rt = ET.SubElement(rs, f"{{{OTA_NS}}}RoomTypes")
        ET.SubElement(rt, f"{{{OTA_NS}}}RoomType", {"RoomTypeCode": stay["room_type_code"]})
        rp = ET.SubElement(rs, f"{{{OTA_NS}}}RatePlans")
        ET.SubElement(rp, f"{{{OTA_NS}}}RatePlan", {"RatePlanCode": stay["rate_plan_code"]})
        gc = ET.SubElement(rs, f"{{{OTA_NS}}}GuestCounts")
        ET.SubElement(gc, f"{{{OTA_NS}}}GuestCount", {"AgeQualifyingCode": "10", "Count": str(stay.get("adults", 1))})
        if stay.get("children"):
            ET.SubElement(gc, f"{{{OTA_NS}}}GuestCount", {"AgeQualifyingCode": "8", "Count": str(stay["children"])})
        ts = ET.SubElement(rs, f"{{{OTA_NS}}}TimeSpan", {"Start": str(stay["arrival"]), "End": str(stay["departure"])})
        _ = ts
        total = ET.SubElement(rs, f"{{{OTA_NS}}}Total", {"AmountAfterTax": f"{stay['total_amount']:.2f}", "CurrencyCode": stay.get("currency", "TRY")})
        _ = total

    # ResGuests
    primary = p.get("primary_guest") or {}
    rgs = ET.SubElement(hr, f"{{{OTA_NS}}}ResGuests")
    rg = ET.SubElement(rgs, f"{{{OTA_NS}}}ResGuest", {"PrimaryIndicator": "true", "ResGuestRPH": "1"})
    profiles = ET.SubElement(rg, f"{{{OTA_NS}}}Profiles")
    profile_info = ET.SubElement(profiles, f"{{{OTA_NS}}}ProfileInfo")
    profile = ET.SubElement(profile_info, f"{{{OTA_NS}}}Profile", {"ProfileType": "1"})  # 1 = Customer
    customer = ET.SubElement(profile, f"{{{OTA_NS}}}Customer")
    person_name = ET.SubElement(customer, f"{{{OTA_NS}}}PersonName")
    if primary.get("given_name"):
        ET.SubElement(person_name, f"{{{OTA_NS}}}GivenName").text = primary["given_name"]
    ET.SubElement(person_name, f"{{{OTA_NS}}}Surname").text = primary.get("surname", "")
    if primary.get("email"):
        e = ET.SubElement(customer, f"{{{OTA_NS}}}Email")
        e.text = primary["email"]
    if primary.get("phone"):
        ET.SubElement(customer, f"{{{OTA_NS}}}Telephone", {"PhoneNumber": primary["phone"]})

    return root


# ── Posting (folio charge/payment) ───────────────────────────────
def _build_posting(env: XchangeEnvelope) -> ET.Element:
    p = env.payload
    root = _root("OTA_HotelPostingRQ", env)
    postings = ET.SubElement(root, f"{{{OTA_NS}}}Postings")
    posting = ET.SubElement(
        postings,
        f"{{{OTA_NS}}}Posting",
        {
            "FolioID": p["folio_id"],
            "TransactionCode": p["transaction_code"],
            "PostingType": p["posting_type"],
        },
    )
    if p.get("reservation_id"):
        ET.SubElement(posting, f"{{{OTA_NS}}}ReservationID", {"ID": p["reservation_id"]})
    amt = ET.SubElement(
        posting,
        f"{{{OTA_NS}}}Amount",
        {
            "Value": f"{p['amount']:.2f}",
            "CurrencyCode": p.get("currency", "TRY"),
        },
    )
    _ = amt
    desc = ET.SubElement(posting, f"{{{OTA_NS}}}Description")
    desc.text = p.get("description", "")
    return root


# ── Inventory ────────────────────────────────────────────────────
def _build_inventory(env: XchangeEnvelope) -> ET.Element:
    p = env.payload
    root = _root("OTA_HotelInvCountNotifRQ", env)
    invs = ET.SubElement(root, f"{{{OTA_NS}}}Inventories")
    inv = ET.SubElement(invs, f"{{{OTA_NS}}}Inventory")
    sa = ET.SubElement(
        inv,
        f"{{{OTA_NS}}}StatusApplicationControl",
        {
            "Start": str(p["business_date"]),
            "End": str(p["business_date"]),
            "InvTypeCode": p["room_type_code"],
        },
    )
    _ = sa
    counts = ET.SubElement(inv, f"{{{OTA_NS}}}InvCounts")
    ET.SubElement(
        counts,
        f"{{{OTA_NS}}}InvCount",
        {
            "CountType": "2",
            "Count": str(p["available_count"]),
        },
    )
    return root


# ── Rate ─────────────────────────────────────────────────────────
def _build_rate(env: XchangeEnvelope) -> ET.Element:
    p = env.payload
    root = _root("OTA_HotelRateAmountNotifRQ", env)
    rates = ET.SubElement(root, f"{{{OTA_NS}}}RateAmountMessages")
    rm = ET.SubElement(rates, f"{{{OTA_NS}}}RateAmountMessage")
    sa = ET.SubElement(
        rm,
        f"{{{OTA_NS}}}StatusApplicationControl",
        {
            "Start": str(p["business_date"]),
            "End": str(p["business_date"]),
            "InvTypeCode": p["room_type_code"],
            "RatePlanCode": p["rate_plan_code"],
        },
    )
    _ = sa
    rates_el = ET.SubElement(rm, f"{{{OTA_NS}}}Rates")
    rate = ET.SubElement(rates_el, f"{{{OTA_NS}}}Rate")
    base = ET.SubElement(rate, f"{{{OTA_NS}}}BaseByGuestAmts")
    ET.SubElement(
        base,
        f"{{{OTA_NS}}}BaseByGuestAmt",
        {
            "AmountAfterTax": f"{p['amount']:.2f}",
            "CurrencyCode": p.get("currency", "TRY"),
        },
    )
    return root


# ── Generic fallback ─────────────────────────────────────────────
def _build_generic(env: XchangeEnvelope) -> ET.Element:
    root = ET.Element(
        f"{{{HTNG_NS}}}SyroceMessage",
        {
            "MessageID": env.message_id,
            "MessageType": env.message_type.value,
            "TimeStamp": _utc_iso(env.occurred_at),
            "TenantID": env.tenant_id,
        },
    )
    payload_el = ET.SubElement(root, f"{{{HTNG_NS}}}Payload")
    _payload_to_xml(payload_el, env.payload, ns=HTNG_NS)
    return root


def _payload_to_xml(parent: ET.Element, value: Any, *, ns: str, name: str | None = None) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            child = ET.SubElement(parent, f"{{{ns}}}{k}")
            _payload_to_xml(child, v, ns=ns)
    elif isinstance(value, list):
        for item in value:
            child = ET.SubElement(parent, f"{{{ns}}}Item")
            _payload_to_xml(child, item, ns=ns)
    else:
        parent.text = "" if value is None else str(value)


# ── Public API ───────────────────────────────────────────────────
_BUILDERS = {
    MessageType.RESERVATION_CREATE: _build_reservation,
    MessageType.RESERVATION_MODIFY: _build_reservation,
    MessageType.RESERVATION_CANCEL: _build_reservation,
    MessageType.POSTING_CHARGE: _build_posting,
    MessageType.POSTING_PAYMENT: _build_posting,
    MessageType.INVENTORY_UPDATE: _build_inventory,
    MessageType.RATE_UPDATE: _build_rate,
}


def serialize(envelope: XchangeEnvelope) -> str:
    """Render an HTNG/OTA-XML string for a canonical message."""
    ET.register_namespace("ota", OTA_NS)
    ET.register_namespace("htng", HTNG_NS)
    builder = _BUILDERS.get(envelope.message_type, _build_generic)
    root = builder(envelope)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
