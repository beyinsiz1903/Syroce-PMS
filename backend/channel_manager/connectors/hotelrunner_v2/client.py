"""
HotelRunner v2 — HTTP Client
==============================

Single responsibility: make authenticated HTTP calls to HotelRunner REST API.
No business logic. No mapping. No retries (caller handles that).

Auth: token + hr_id as query params on every request.
Timeouts: connect 5s, read 20s.
Every response → typed Result dataclass.
"""

import logging
import time
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from .errors import (
    HRv2AuthError,
    HRv2ParseError,
    HRv2RateLimitError,
    HRv2ServerError,
    HRv2TimeoutError,
    HRv2ValidationError,
)

logger = logging.getLogger("hrv2.client")

_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


@dataclass
class HRv2Response:
    """Structured result from every HTTP call."""

    success: bool
    status_code: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0
    correlation_id: str = ""


class HRv2Client:
    """
    Async HTTP client for HotelRunner REST API.

    Usage:
        client = HRv2Client(token="...", hr_id="...", base_url="...")
        resp = await client.get("/infos/channels")
    """

    def __init__(self, token: str, hr_id: str, base_url: str):
        if not token or not hr_id:
            raise HRv2AuthError("token and hr_id are required")
        self._token = token
        self._hr_id = hr_id
        self._base_url = base_url.rstrip("/")

    def _auth_params(self) -> dict[str, str]:
        return {"token": self._token, "hr_id": self._hr_id}

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self._base_url}{path}"

    async def get(self, path: str, *, params: dict[str, str] | None = None, correlation_id: str = "") -> HRv2Response:
        return await self._request("GET", path, params=params, correlation_id=correlation_id)

    async def put(self, path: str, *, params: dict[str, str] | None = None, json_body: dict | None = None, form_data: dict | None = None, correlation_id: str = "") -> HRv2Response:
        return await self._request("PUT", path, params=params, json_body=json_body, form_data=form_data, correlation_id=correlation_id)

    async def post(self, path: str, *, params: dict[str, str] | None = None, json_body: dict | None = None, form_data: dict | None = None, correlation_id: str = "") -> HRv2Response:
        return await self._request("POST", path, params=params, json_body=json_body, form_data=form_data, correlation_id=correlation_id)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict | None = None,
        form_data: dict | None = None,
        correlation_id: str = "",
    ) -> HRv2Response:
        corr_id = correlation_id or str(_uuid.uuid4())[:12]
        url = self._url(path)
        merged = {**self._auth_params(), **(params or {})}
        start = time.monotonic()

        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            try:
                kwargs: dict[str, Any] = {"params": merged}
                if json_body is not None:
                    kwargs["json"] = json_body
                elif form_data is not None:
                    kwargs["data"] = form_data

                if method == "GET":
                    resp = await http.get(url, **kwargs)
                elif method == "PUT":
                    resp = await http.put(url, **kwargs)
                elif method == "POST":
                    resp = await http.post(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                dur = int((time.monotonic() - start) * 1000)
                logger.info("[HRv2] %s %s → %d (%dms) [%s]", method, path, resp.status_code, dur, corr_id)

                self._raise_for_status(resp, corr_id)

                try:
                    data = resp.json()
                except Exception:
                    raise HRv2ParseError(f"Invalid JSON from {path}")

                if data.get("status") == "error":
                    return HRv2Response(success=False, status_code=resp.status_code, data=data, error=data.get("error", "API error"), duration_ms=dur, correlation_id=corr_id)

                return HRv2Response(success=True, status_code=resp.status_code, data=data, duration_ms=dur, correlation_id=corr_id)

            except (HRv2AuthError, HRv2RateLimitError, HRv2ServerError, HRv2ValidationError, HRv2ParseError):
                raise
            except httpx.ConnectError:
                raise HRv2TimeoutError(f"Cannot connect to HotelRunner ({path})")
            except httpx.TimeoutException:
                raise HRv2TimeoutError(f"Timeout on {path}")

    @staticmethod
    def _raise_for_status(resp: httpx.Response, corr_id: str) -> None:
        code = resp.status_code
        if 200 <= code < 300:
            return
        if code in (401, 403):
            raise HRv2AuthError(f"Auth failed ({code}) [{corr_id}]")
        if code == 429:
            retry = int(resp.headers.get("Retry-After", "60"))
            raise HRv2RateLimitError(f"Rate limited [{corr_id}]", retry_after=retry)
        if code == 400:
            raise HRv2ValidationError(f"Bad request ({code}) [{corr_id}]: {resp.text[:300]}")
        if code >= 500:
            raise HRv2ServerError(f"Server error ({code}) [{corr_id}]")
        if code >= 400:
            raise HRv2ValidationError(f"Client error ({code}) [{corr_id}]")
