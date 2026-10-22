"""Read-only Exely Connect client. Never reuses PMSConnect credentials or URLs."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx

from core.secrets import get_secrets_manager
from integrations.xchange import safety

from .production_safety import reservation_sync_block_reason

VAULT_PROVIDER = "exely-read-reservation"
ORIGINS = {
    "sandbox": "https://connect.test.hopenapi.com",
    "production": "https://connect.hopenapi.com",
}
BOOKING_NUMBER = re.compile(r"^[A-Za-z0-9_-]{1,160}$")


class ReadReservationError(RuntimeError):
    """Only stable codes cross the API/log boundary; no provider bodies or keys."""


def origin_for(connection: dict[str, Any]) -> str:
    mode = connection.get("mode")
    if mode not in ORIGINS or not connection.get("hotel_code") or not connection.get("id"):
        raise ReadReservationError("EXELY_READ_CONNECTION_SCOPE_INVALID")
    if not re.fullmatch(r"[0-9]{1,32}", str(connection["hotel_code"])):
        raise ReadReservationError("EXELY_READ_PROPERTY_INVALID")
    return ORIGINS[mode]


def require_read_allowed() -> None:
    reason = reservation_sync_block_reason()
    if reason:
        raise ReadReservationError(reason)
    if os.getenv("E2E_EXTERNAL_DRY_RUN", "").lower() in {"true", "1"}:
        raise ReadReservationError("EXELY_READ_DRY_RUN")


class ReadReservationClient:
    def __init__(self, connection: dict[str, Any], credentials: dict[str, str], request=None):
        self.origin = origin_for(connection)
        self.property_id = str(connection["hotel_code"])
        self._credentials = credentials
        self._request = request or safety.safe_request_async
        self._token = ""
        self._expires_at = 0.0
        self._last_booking_read = 0.0

    async def _json(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        require_read_allowed()
        try:
            response = await self._request(method, self.origin + path, timeout=20, max_response_bytes=2_000_000, follow_redirects=False, **kwargs)
            if response.status_code != 200:
                raise ReadReservationError(f"EXELY_READ_HTTP_{response.status_code}")
            if len(response.content) > 2_000_000:
                raise ReadReservationError("EXELY_READ_RESPONSE_TOO_LARGE")
            result = json.loads(response.content)
        except ReadReservationError:
            raise
        except safety.EgressDenied:
            raise ReadReservationError("EXELY_READ_EGRESS_DENIED") from None
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise ReadReservationError("EXELY_READ_RESPONSE_UNAVAILABLE") from None
        if not isinstance(result, dict):
            raise ReadReservationError("EXELY_READ_RESPONSE_INVALID")
        return result

    async def authenticate(self) -> None:
        if self._token and time.monotonic() < self._expires_at:
            return
        result = await self._json("POST", "/auth/token", data={
            "grant_type": "client_credentials",
            "client_id": self._credentials["client_id"],
            "client_secret": self._credentials["client_secret"],
        })
        token, lifetime = result.get("access_token"), result.get("expires_in")
        if not isinstance(token, str) or not token or len(token) > 32768 or type(lifetime) is not int or lifetime <= 30:
            raise ReadReservationError("EXELY_READ_TOKEN_INVALID")
        self._token = token
        self._expires_at = time.monotonic() + min(lifetime - 30, 840)

    async def booking(self, number: str) -> dict[str, Any]:
        if not BOOKING_NUMBER.fullmatch(number):
            raise ReadReservationError("EXELY_READ_BOOKING_NUMBER_INVALID")
        await self.authenticate()
        # The provider permits ten detail reads/second. Pace a serial batch;
        # a shared quota rejection still stops it without an automatic retry.
        delay = self._last_booking_read + 0.11 - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_booking_read = time.monotonic()
        result = await self._json(
            "GET", f"/api/read-reservation/v1/properties/{self.property_id}/bookings/{number}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        booking = result.get("booking")
        if not isinstance(booking, dict) or str(booking.get("propertyId")) != self.property_id or booking.get("number") != number:
            raise ReadReservationError("EXELY_READ_BOOKING_SCOPE_MISMATCH")
        return booking


@asynccontextmanager
async def read_client(connection: dict[str, Any], credentials: dict[str, str]):
    # The common safety layer owns pinned transport creation and cleanup.
    yield ReadReservationClient(connection, credentials)


async def saved_read_credentials(tenant_id: str, connection: dict[str, Any]) -> dict[str, str] | None:
    if connection.get("tenant_id") != tenant_id:
        raise ReadReservationError("EXELY_READ_CONNECTION_TENANT_MISMATCH")
    if not connection.get("read_reservation_enabled"):
        return None
    origin_for(connection)
    credentials = await get_secrets_manager().get_provider_credentials(
        tenant_id, VAULT_PROVIDER, str(connection["hotel_code"]), actor="exely_read_reservation",
    )
    if not credentials:
        raise ReadReservationError("EXELY_READ_CREDENTIALS_UNAVAILABLE")
    if any(credentials.get(key) != str(connection.get(field) or "") for key, field in (
        ("connection_id", "id"), ("property_id", "hotel_code"), ("mode", "mode"),
    )) or not credentials.get("client_id") or not credentials.get("client_secret"):
        raise ReadReservationError("EXELY_READ_CREDENTIAL_SCOPE_MISMATCH")
    return credentials
