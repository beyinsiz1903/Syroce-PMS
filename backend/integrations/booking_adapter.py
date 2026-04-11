"""Booking.com Channel Adapter

This module defines a BookingAdapter class that acts as an abstraction layer
between the internal Channel Manager rate/availability payloads and the
Booking.com connectivity API payloads.

For now, this is a skeleton that **normalizes** the internal data and logs it.
Real HTTP calls to Booking.com can be added later in a controlled way.
"""
from typing import Any

from _legacy.booking_availability import normalize_availability_response


class BookingAdapter:
    def __init__(self, connection: dict[str, Any]):
        """Initialize adapter with channel connection config.

        connection example:
        {
            "channel_type": "booking_com",
            "channel_name": "Booking.com",
            "api_endpoint": "https://distribution-xml.booking.com/",
            "api_key": "...",
            "property_id": "...",
            ...
        }
        """
        self.connection = connection or {}

    def normalize_rate_update(self, rate_update: dict[str, Any]) -> dict[str, Any]:
        """Normalize internal rate_update payload into a Booking-like structure.

        This does **not** call the real Booking API yet. It only prepares a
        structured payload that can later be used by the actual integration.

        rate_update example:
        {
            "room_type": "Deluxe Double",
            "date_from": "2025-01-01",
            "date_to": "2025-01-07",
            "base_rate": 1500.0,
            "discount_pct": 10.0,
            "new_rate": 1350.0,
            "channels": ["booking_com"],
        }
        """
        room_type = rate_update.get("room_type")
        date_from = rate_update.get("date_from")
        date_to = rate_update.get("date_to")
        new_rate = rate_update.get("new_rate")

        # In a real integration, we would map PMS room_type -> Booking room id
        # via room mappings and also handle currency/tax settings.
        payload: dict[str, Any] = {
            "property_id": self.connection.get("property_id"),
            "room_type": room_type,
            "date_from": date_from,
            "date_to": date_to,
            "rate": new_rate,
            "currency": self.connection.get("currency", "TRY"),
            "meta": {
                "base_rate": rate_update.get("base_rate"),
                "discount_pct": rate_update.get("discount_pct"),
                "channels": rate_update.get("channels", []),
            },
        }
        return payload

    async def push_rates(self, rate_update: dict[str, Any]) -> dict[str, Any]:
        """Simulate pushing rates to Booking.com.

        For now this only returns a normalized payload. Real HTTP calls
        and error handling can be added later.
        """
        normalized = self.normalize_rate_update(rate_update)
        # TODO: Implement real Booking.com API call here in the future.
        return {
            "status": "simulated",
            "normalized_payload": normalized,
        }

    async def push_availability(self, availability_update: dict[str, Any]) -> dict[str, Any]:
        """Simulate pushing availability updates to Booking.com.

        `availability_update` is expected to contain:
        {
          "rooms": [ ... /pms/rooms/availability result ... ],
          "check_in": "YYYY-MM-DD",
          "check_out": "YYYY-MM-DD",
        }
        """
        rooms = availability_update.get("rooms", [])
        check_in = availability_update.get("check_in", "")
        check_out = availability_update.get("check_out", "")

        normalized = normalize_availability_response(rooms, check_in, check_out)
        # TODO: Implement real Booking.com API call here in the future.
        return {
            "status": "simulated",
            "normalized_payload": normalized,
        }

    async def import_reservations(self, since: str) -> list[dict[str, Any]]:
        """Simulate pulling reservations from Booking.com.

        This is a placeholder for future work.
        """
        # TODO: Implement when Booking.com pull model is required.
        return []
