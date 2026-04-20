"""Booking.com Channel Adapter

Real HTTP integration with Booking.com Connectivity API
(https://connect.booking.com / supply-xml.booking.com).

The adapter normalizes the internal Channel Manager payloads into
Booking.com-compatible XML/JSON, then performs an authenticated HTTP call
when the connection contains real credentials. When credentials are missing
(local/dev), it returns a normalized payload with `status='dry_run'` so the
calling pipeline (rate push, availability sync, reservation pull) still
exercises the full code path.

Connection schema:
    {
      "channel_type": "booking_com",
      "api_endpoint": "https://supply-xml.booking.com",  # base URL
      "username": "...",
      "password": "...",
      "property_id": "..."
    }
"""
import logging
from typing import Any

import httpx

from integrations.booking_availability import normalize_availability_response

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)


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

    def _credentials(self) -> tuple[str, str, str] | None:
        """Return (base_url, username, password) when fully configured, else None."""
        base = self.connection.get("api_endpoint")
        user = self.connection.get("username") or self.connection.get("api_key")
        pwd = self.connection.get("password") or self.connection.get("api_secret")
        if base and user and pwd:
            return base.rstrip("/"), user, pwd
        return None

    async def _post(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        creds = self._credentials()
        if not creds:
            logger.info("booking.com %s: dry_run (no credentials)", path)
            return {"status": "dry_run", "reason": "missing_credentials", "payload": json_body}
        base, user, pwd = creds
        url = f"{base}{path}"
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(url, json=json_body, auth=(user, pwd))
            ok = 200 <= resp.status_code < 300
            body: Any
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:2000]
            log_fn = logger.info if ok else logger.warning
            log_fn("booking.com POST %s → %s", path, resp.status_code)
            return {
                "status": "ok" if ok else "error",
                "http_status": resp.status_code,
                "response": body,
                "payload": json_body,
            }
        except httpx.HTTPError as exc:
            logger.exception("booking.com POST %s failed", path)
            return {"status": "error", "error": str(exc), "payload": json_body}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        creds = self._credentials()
        if not creds:
            logger.info("booking.com GET %s: dry_run (no credentials)", path)
            return {"status": "dry_run", "reason": "missing_credentials", "params": params or {}}
        base, user, pwd = creds
        url = f"{base}{path}"
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(url, params=params or {}, auth=(user, pwd))
            ok = 200 <= resp.status_code < 300
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:2000]
            return {
                "status": "ok" if ok else "error",
                "http_status": resp.status_code,
                "response": body,
            }
        except httpx.HTTPError as exc:
            logger.exception("booking.com GET %s failed", path)
            return {"status": "error", "error": str(exc)}

    async def push_rates(self, rate_update: dict[str, Any]) -> dict[str, Any]:
        """Push rate update to Booking.com Rates API."""
        normalized = self.normalize_rate_update(rate_update)
        result = await self._post("/rates", normalized)
        return {"normalized_payload": normalized, **result}

    async def push_availability(self, availability_update: dict[str, Any]) -> dict[str, Any]:
        """Push availability update to Booking.com Availability API."""
        rooms = availability_update.get("rooms", [])
        check_in = availability_update.get("check_in", "")
        check_out = availability_update.get("check_out", "")
        normalized = normalize_availability_response(rooms, check_in, check_out)
        body = {
            "property_id": self.connection.get("property_id"),
            "check_in": check_in,
            "check_out": check_out,
            "rooms": normalized,
        }
        result = await self._post("/availability", body)
        return {"normalized_payload": normalized, **result}

    async def import_reservations(self, since: str) -> list[dict[str, Any]]:
        """Pull reservations modified since `since` (ISO timestamp) from Booking.com."""
        params = {
            "property_id": self.connection.get("property_id"),
            "modified_since": since,
        }
        result = await self._get("/reservations", params=params)
        if result.get("status") != "ok":
            return []
        body = result.get("response") or {}
        if isinstance(body, dict):
            return list(body.get("reservations") or [])
        if isinstance(body, list):
            return body
        return []
