"""
HotelRunner Provider — Response Parsers
=========================================

Safe response parsing with validation.
Each parser takes raw API data and returns typed schemas.
"""
import logging
from typing import Any, Dict, List

from .schemas import (
    HotelRunnerRoom,
    HotelRunnerChannel,
    HotelRunnerConnectedChannel,
    HotelRunnerReservation,
    HotelRunnerReservationPage,
)
from .errors import HotelRunnerParseError

logger = logging.getLogger("hotelrunner.parser")


def parse_rooms_response(data: Dict[str, Any]) -> List[HotelRunnerRoom]:
    """Parse GET /rooms response into typed room list."""
    rooms_raw = data.get("rooms", [])
    if not isinstance(rooms_raw, list):
        raise HotelRunnerParseError(
            "Expected 'rooms' to be a list",
            raw_response=str(data)[:500],
        )
    rooms = []
    for r in rooms_raw:
        try:
            rooms.append(HotelRunnerRoom(
                inv_code=str(r.get("inv_code", "") or r.get("code", "")),
                name=str(r.get("name", "") or r.get("name_presentation", "")),
                rate_plans=r.get("rate_plans", []),
                channel_codes=r.get("channel_codes", []),
                raw=r,
            ))
        except Exception as e:
            logger.warning("Failed to parse room: %s — %s", r, e)
    return rooms


def parse_channels_response(data: Dict[str, Any]) -> List[HotelRunnerChannel]:
    """Parse GET /infos/channels response."""
    channels_raw = data.get("channels", [])
    if not isinstance(channels_raw, list):
        raise HotelRunnerParseError(
            "Expected 'channels' to be a list",
            raw_response=str(data)[:500],
        )
    channels = []
    for c in channels_raw:
        channels.append(HotelRunnerChannel(
            code=str(c.get("code", "")),
            name=str(c.get("name", "")),
            raw=c,
        ))
    return channels


def parse_connected_channels_response(data: Dict[str, Any]) -> List[HotelRunnerConnectedChannel]:
    """Parse GET /infos/connected_channels response."""
    items = data.get("connected_channels", data.get("channels", []))
    if not isinstance(items, list):
        raise HotelRunnerParseError(
            "Expected connected channels list",
            raw_response=str(data)[:500],
        )
    result = []
    for c in items:
        result.append(HotelRunnerConnectedChannel(
            code=str(c.get("code", "")),
            name=str(c.get("name", "")),
            status=str(c.get("status", "")),
            raw=c,
        ))
    return result


def parse_reservations_response(data: Dict[str, Any]) -> HotelRunnerReservationPage:
    """Parse GET /reservations response into typed page."""
    reservations_raw = data.get("reservations", [])
    if not isinstance(reservations_raw, list):
        raise HotelRunnerParseError(
            "Expected 'reservations' to be a list",
            raw_response=str(data)[:500],
        )

    reservations = []
    for r in reservations_raw:
        try:
            guest = r.get("guest", r.get("address", {})) or {}
            rooms = r.get("rooms", [])
            first_room = rooms[0] if rooms else {}

            reservations.append(HotelRunnerReservation(
                reservation_id=str(r.get("reservation_id", "")),
                hr_number=str(r.get("hr_number", "")),
                status=str(r.get("state", r.get("status", "confirmed"))),
                guest_firstname=str(r.get("firstname", guest.get("first_name", ""))),
                guest_lastname=str(r.get("lastname", guest.get("last_name", ""))),
                guest_email=str((r.get("address") or {}).get("email", guest.get("email", ""))),
                guest_phone=str((r.get("address") or {}).get("phone", guest.get("phone", ""))),
                check_in=str(r.get("checkin_date", r.get("check_in", ""))),
                check_out=str(r.get("checkout_date", r.get("check_out", ""))),
                room_type_code=str(first_room.get("inv_code", r.get("room_type", ""))),
                rate_plan_code=str(first_room.get("rate_plan_code", r.get("rate_plan", ""))),
                adults=int(first_room.get("total_adult", r.get("adults", 1)) or 1),
                children=len(first_room.get("child_ages", [])) or int(r.get("children", 0)),
                total_amount=float(r.get("total", 0) or 0),
                currency=str(r.get("currency", "TRY")),
                channel=str(r.get("channel_display", r.get("channel", ""))),
                message_uid=str(r.get("message_uid", "")),
                last_modified=str(r.get("updated_at", r.get("last_modified", ""))),
                requires_response=bool(r.get("requires_response", False)),
                raw=r,
            ))
        except Exception as e:
            ext_id = r.get("hr_number", r.get("reservation_id", "?"))
            logger.warning("Failed to parse reservation %s: %s", ext_id, e)

    return HotelRunnerReservationPage(
        reservations=reservations,
        current_page=int(data.get("page", data.get("current_page", 1)) or 1),
        total_pages=int(data.get("pages", data.get("total_pages", 1)) or 1),
        total_count=int(data.get("total_count", len(reservations))),
    )
