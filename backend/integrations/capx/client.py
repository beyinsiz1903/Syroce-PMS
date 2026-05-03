"""CapX B2B Network HMAC client.

Spec (üreticiden):
  Base: <CAPX_BASE_URL>/api/integrations/v1/pms

  Auth modları:
    - JWT (otel kullanıcısı)            → connect/status/callback/disconnect/recent
    - Bearer API key                    → POST /availability/sync
    - Bearer + HMAC SHA-256 (X-CapX-*)  → POST /reservation/event

  HMAC payload: raw request body (UTF-8 bytes)
  Header: X-CapX-Signature: sha256=<hex>
  Idempotency: X-CapX-Event-Id (UUID4 per event)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CapXError(Exception):
    """CapX API error wrapper."""

    def __init__(self, message: str, status_code: int = 0, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class CapXClient:
    """Async CapX integration client.

    Reads credentials from os.environ at construction:
      - CAPX_BASE_URL
      - CAPX_API_KEY        (Bearer for availability/sync, reservation/event)
      - CAPX_WEBHOOK_SECRET (HMAC for reservation/event)
    """

    PATH_AVAILABILITY = "/api/integrations/v1/pms/availability/sync"
    PATH_RESERVATION = "/api/integrations/v1/pms/reservation/event"
    PATH_STATUS = "/api/integrations/v1/pms/status"
    PATH_RECENT = "/api/integrations/v1/pms/recent"

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None,
                 webhook_secret: str | None = None, timeout: float = 15.0):
        self.base_url = (base_url or os.getenv("CAPX_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("CAPX_API_KEY", "")
        self.webhook_secret = webhook_secret or os.getenv("CAPX_WEBHOOK_SECRET", "")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _sign(self, body_bytes: bytes) -> str:
        if not self.webhook_secret:
            raise CapXError("CAPX_WEBHOOK_SECRET not set")
        digest = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    def _bearer_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise CapXError("CAPX_API_KEY not set")
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _post(self, path: str, body: dict[str, Any], *, sign: bool = False,
                    event_id: str | None = None, jwt_token: str | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise CapXError("CAPX_BASE_URL not set")

        url = f"{self.base_url}{path}"
        body_bytes = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"
        else:
            headers.update(self._bearer_headers())
        if sign:
            headers["X-CapX-Signature"] = self._sign(body_bytes)
            headers["X-CapX-Event-Id"] = event_id or str(uuid.uuid4())

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, content=body_bytes, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("CapX network error %s: %s", path, exc)
            raise CapXError(f"network error: {exc}") from exc

        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            logger.warning("CapX %s -> %d: %s", path, resp.status_code, err_body)
            raise CapXError(f"{resp.status_code} {path}", status_code=resp.status_code, body=err_body)

        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text, "status_code": resp.status_code}

    async def _get(self, path: str, *, jwt_token: str | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise CapXError("CAPX_BASE_URL not set")
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"
        else:
            headers.update(self._bearer_headers())
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise CapXError(f"network error: {exc}") from exc
        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            raise CapXError(f"{resp.status_code} {path}", status_code=resp.status_code, body=err_body)
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    # ── Public API ────────────────────────────────────────────────

    async def push_availability(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Push PMS availability snapshot.

        snapshot shape (üretici örnek):
          {
            "hotel_id": "...",
            "room_type": "DBL_STD",
            "start_date": "2026-05-10",
            "end_date":   "2026-05-15",
            "available_count": 8,
            "price_min": 2500.0,
            "price_max": 3200.0,
            "currency": "TRY",
            "auto_publish": true,
            "pms_external_ref": "syroce-room-DBL_STD-20260510"
          }
        """
        return await self._post(self.PATH_AVAILABILITY, snapshot)

    async def push_reservation_event(self, event: dict[str, Any], *,
                                      event_id: str | None = None) -> dict[str, Any]:
        """Push booking lifecycle event (created / cancelled / no_show).

        event shape:
          {
            "event_type": "created" | "cancelled" | "no_show",
            "pms_external_ref": "syroce-listing-...",
            "booking_id": "...",
            "guest_name": "...",
            "check_in":  "2026-05-10",
            "check_out": "2026-05-15",
            "amount":    3200.0,
            "currency":  "TRY",
            "occurred_at": "2026-05-03T16:30:00Z"
          }

        Headers added: X-CapX-Signature (HMAC of body), X-CapX-Event-Id (UUID4)
        """
        return await self._post(
            self.PATH_RESERVATION, event, sign=True, event_id=event_id
        )

    async def get_status(self, jwt_token: str) -> dict[str, Any]:
        """JWT-authenticated status check (otel kullanıcısı)."""
        return await self._get(self.PATH_STATUS, jwt_token=jwt_token)

    async def get_recent(self, jwt_token: str) -> dict[str, Any]:
        return await self._get(self.PATH_RECENT, jwt_token=jwt_token)


_singleton: CapXClient | None = None


def get_capx_client(refresh: bool = False) -> CapXClient:
    """Module-level singleton factory.

    Pass refresh=True after credentials are saved at runtime to rebuild
    the client with new env values.
    """
    global _singleton
    if _singleton is None or refresh:
        _singleton = CapXClient()
    return _singleton
