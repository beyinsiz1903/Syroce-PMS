"""
HotelRunner HTTP Client - Production-grade API client with rate limiting, retry, and structured error handling.

This is the ONLY module that makes HTTP calls to HotelRunner.
All other modules interact through this client.
"""
import logging
import time
from typing import Dict, Any, Optional

import httpx

from .auth import HotelRunnerAuth
from .rate_limit import RateLimiter
from .retry_policy import RetryPolicy
from .errors import (
    ConnectorError, AuthenticationError, RateLimitError,
    ProviderUnavailableError, XmlParseError,
)
from . import xml_builder, xml_parser

logger = logging.getLogger("channel_manager.hotelrunner.client")

# HotelRunner API base URLs
HOTELRUNNER_API_BASE = "https://app.hotelrunner.com/api/v2"
HOTELRUNNER_SANDBOX_BASE = "https://sandbox.hotelrunner.com/api/v2"


class HotelRunnerClient:
    """
    Production-grade async HTTP client for HotelRunner API.

    Features:
      - Token-based authentication
      - Rate limiting (token bucket)
      - Automatic retry with exponential backoff
      - Structured error handling
      - Request/response logging
      - Sandbox mode for development
    """

    def __init__(
        self,
        auth: HotelRunnerAuth,
        sandbox: bool = True,
        rate_limiter: Optional[RateLimiter] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        self._auth = auth
        self._base_url = HOTELRUNNER_SANDBOX_BASE if sandbox else HOTELRUNNER_API_BASE
        self._rate_limiter = rate_limiter or RateLimiter()
        self._retry_policy = retry_policy or RetryPolicy()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        self._sandbox = sandbox

    async def close(self):
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        xml_body: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> str:
        """Make an authenticated request to HotelRunner API."""
        # Rate limit
        acquired = await self._rate_limiter.acquire(timeout=120)
        if not acquired:
            raise RateLimitError(retry_after_seconds=60, message="Local rate limit exceeded")

        url = f"{self._base_url}{path}"
        merged_params = {**(params or {}), **self._auth.get_auth_params()}
        headers = self._auth.get_auth_headers()

        start = time.monotonic()
        try:
            if method.upper() == "POST":
                response = await self._client.post(
                    url, content=xml_body, headers=headers, params=merged_params,
                )
            else:
                response = await self._client.get(
                    url, headers=headers, params=merged_params,
                )

            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "HR API %s %s -> %d (%dms)",
                method, path, response.status_code, duration_ms,
            )

            if response.status_code == 401:
                raise AuthenticationError("HotelRunner returned 401")
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                raise RateLimitError(retry_after_seconds=retry_after)
            if response.status_code >= 500:
                raise ProviderUnavailableError(f"HotelRunner returned {response.status_code}")
            if response.status_code >= 400:
                raise ConnectorError(
                    f"HotelRunner returned {response.status_code}: {response.text[:500]}",
                    recoverable=False,
                )

            return response.text

        except httpx.ConnectError:
            raise ProviderUnavailableError("Cannot connect to HotelRunner API")
        except httpx.TimeoutException:
            raise ProviderUnavailableError("HotelRunner API request timed out")

    async def push_availability(self, updates: list) -> Dict[str, Any]:
        """Push inventory availability to HotelRunner."""
        xml_body = xml_builder.build_availability_notif(
            hr_id=self._auth.hr_id,
            updates=updates,
        )

        async def _do():
            resp_xml = await self._request("POST", "/ari/availability", xml_body=xml_body)
            return xml_parser.parse_response_status(resp_xml)

        return await self._retry_policy.execute_with_retry(_do)

    async def push_rates(self, updates: list) -> Dict[str, Any]:
        """Push rate amounts to HotelRunner."""
        xml_body = xml_builder.build_rate_amount_notif(
            hr_id=self._auth.hr_id,
            updates=updates,
        )

        async def _do():
            resp_xml = await self._request("POST", "/ari/rates", xml_body=xml_body)
            return xml_parser.parse_response_status(resp_xml)

        return await self._retry_policy.execute_with_retry(_do)

    async def pull_reservations(
        self,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
    ) -> list:
        """Pull undelivered reservations from HotelRunner."""
        xml_body = xml_builder.build_read_rq(
            hr_id=self._auth.hr_id,
            date_start=date_start,
            date_end=date_end,
        )

        async def _do():
            resp_xml = await self._request("POST", "/reservations/read", xml_body=xml_body)
            return xml_parser.parse_reservations_response(resp_xml)

        return await self._retry_policy.execute_with_retry(_do)

    async def acknowledge_reservations(self, reservation_ids: list) -> Dict[str, Any]:
        """Acknowledge received reservations to HotelRunner."""
        xml_body = xml_builder.build_notif_report_rq(
            hr_id=self._auth.hr_id,
            reservation_ids=reservation_ids,
        )

        async def _do():
            resp_xml = await self._request("POST", "/reservations/acknowledge", xml_body=xml_body)
            return xml_parser.parse_response_status(resp_xml)

        return await self._retry_policy.execute_with_retry(_do)

    async def test_connection(self) -> Dict[str, Any]:
        """Test connectivity and authentication with HotelRunner."""
        try:
            result = await self.pull_reservations()
            return {"success": True, "message": "Connection successful", "reservations_found": len(result)}
        except AuthenticationError:
            return {"success": False, "message": "Authentication failed - check token and hr_id"}
        except ProviderUnavailableError as e:
            return {"success": False, "message": f"Provider unavailable: {e.message}"}
        except Exception as e:
            return {"success": False, "message": f"Connection test failed: {str(e)}"}
