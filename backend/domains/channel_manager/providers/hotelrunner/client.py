"""
HotelRunner Provider — HTTP Client
====================================

Low-level HTTP client. ONLY module that makes network calls.

Responsibilities:
- Build full URL from base + path
- Attach auth query params
- Enforce timeouts (connect: 5s, read: 20s)
- Map HTTP status codes to typed errors
- Log every request with correlation context
- Support both JSON and form-encoded payloads
"""

import logging
import time
import uuid as _uuid
from dataclasses import dataclass
from typing import Any

import httpx

from . import endpoints as ep
from .auth import build_auth_params, validate_credentials
from .errors import (
    HotelRunnerAuthError,
    HotelRunnerParseError,
    HotelRunnerPayloadError,
    HotelRunnerRateLimitError,
    HotelRunnerTemporaryError,
)

logger = logging.getLogger("hotelrunner.client")

_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


@dataclass
class HttpResult:
    """Structured result from an HTTP call."""

    success: bool
    status_code: int = 0
    data: Any = None
    error: str = ""
    duration_ms: int = 0
    correlation_id: str = ""
    raw_text: str = ""


class HotelRunnerHttpClient:
    """
    Production-grade async HTTP client for HotelRunner API.

    All provider methods go through get() / put() / post().
    Rate limiting is handled externally by the provider layer.
    Uses a shared httpx.AsyncClient for connection pooling.
    """

    def __init__(self, token: str, hr_id: str, base_url: str = ep.BASE_URL):
        validate_credentials(token, hr_id)
        self._token = token
        self._hr_id = hr_id
        self._base_url = base_url.rstrip("/")
        self._shared_client: httpx.AsyncClient | None = None

    def _build_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self._base_url}{path}"

    def _auth_params(self) -> dict[str, str]:
        return build_auth_params(self._token, self._hr_id)

    async def get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        correlation_id: str = "",
    ) -> HttpResult:
        """HTTP GET with auth params."""
        return await self._request("GET", path, params=params, correlation_id=correlation_id)

    async def put(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        correlation_id: str = "",
    ) -> HttpResult:
        """HTTP PUT with auth params."""
        return await self._request(
            "PUT",
            path,
            params=params,
            json_body=json_body,
            form_data=form_data,
            correlation_id=correlation_id,
        )

    async def post(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        correlation_id: str = "",
    ) -> HttpResult:
        """HTTP POST with auth params."""
        return await self._request(
            "POST",
            path,
            params=params,
            json_body=json_body,
            form_data=form_data,
            correlation_id=correlation_id,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Return shared client, creating one if needed."""
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = httpx.AsyncClient(
                timeout=_TIMEOUT,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
                headers={"Accept": "application/json"},
            )
        return self._shared_client

    async def close(self) -> None:
        """Close the shared client."""
        if self._shared_client and not self._shared_client.is_closed:
            await self._shared_client.aclose()
            self._shared_client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        correlation_id: str = "",
    ) -> HttpResult:
        corr_id = correlation_id or str(_uuid.uuid4())[:12]
        url = self._build_url(path)
        merged_params = {**self._auth_params(), **(params or {})}
        start = time.monotonic()

        client = await self._get_client()
        try:
            kwargs: dict[str, Any] = {"params": merged_params}
            if json_body is not None:
                kwargs["json"] = json_body
            elif form_data is not None:
                kwargs["data"] = form_data

            if method == "GET":
                resp = await client.get(url, **kwargs)
            elif method == "PUT":
                resp = await client.put(url, **kwargs)
            elif method == "POST":
                resp = await client.post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")

            duration_ms = int((time.monotonic() - start) * 1000)

            logger.info(
                "[HR] %s %s -> %d (%dms) [%s]",
                method,
                path,
                resp.status_code,
                duration_ms,
                corr_id,
            )

            self._raise_for_status(resp, duration_ms, corr_id)

            try:
                data = resp.json()
            except Exception:
                raise HotelRunnerParseError(
                    f"Invalid JSON response from {path}",
                    raw_response=resp.text[:2000],
                )

            if data.get("status") == "error":
                return HttpResult(
                    success=False,
                    status_code=resp.status_code,
                    data=data,
                    error=data.get("error", "API returned error status"),
                    duration_ms=duration_ms,
                    correlation_id=corr_id,
                    raw_text=resp.text[:2000],
                )

            return HttpResult(
                success=True,
                status_code=resp.status_code,
                data=data,
                duration_ms=duration_ms,
                correlation_id=corr_id,
            )

        except (
            HotelRunnerAuthError,
            HotelRunnerRateLimitError,
            HotelRunnerTemporaryError,
            HotelRunnerPayloadError,
            HotelRunnerParseError,
        ):
            raise
        except httpx.ConnectError:
            duration_ms = int((time.monotonic() - start) * 1000)
            raise HotelRunnerTemporaryError(f"Cannot connect to HotelRunner API ({path})")
        except httpx.TimeoutException:
            duration_ms = int((time.monotonic() - start) * 1000)
            raise HotelRunnerTemporaryError(f"HotelRunner API timeout ({path})")

    @staticmethod
    def _raise_for_status(resp: httpx.Response, duration_ms: int, corr_id: str) -> None:
        """Map HTTP status codes to typed errors."""
        code = resp.status_code
        if 200 <= code < 300:
            return
        if code == 401:
            raise HotelRunnerAuthError(f"Invalid credentials (401) [{corr_id}]")
        if code == 403:
            raise HotelRunnerAuthError(f"Access denied (403) [{corr_id}]")
        if code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            raise HotelRunnerRateLimitError(
                retry_after_seconds=retry_after,
                message=f"Rate limit exceeded (429) [{corr_id}]",
            )
        if code == 400:
            raise HotelRunnerPayloadError(f"Bad request (400) [{corr_id}]: {resp.text[:500]}")
        if code >= 500:
            raise HotelRunnerTemporaryError(f"Server error ({code}) [{corr_id}]")
        if code >= 400:
            raise HotelRunnerPayloadError(f"Client error ({code}) [{corr_id}]: {resp.text[:500]}")
