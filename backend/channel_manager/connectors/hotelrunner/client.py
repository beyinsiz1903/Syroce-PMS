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

    async def _test_single_step(self, step_name: str, method: str, path: str, xml_body: Optional[str] = None) -> Dict[str, Any]:
        """Execute a single test step and capture the result with latency."""
        start = time.monotonic()
        try:
            merged_params = self._auth.get_auth_params()
            headers = self._auth.get_auth_headers()
            url = f"{self._base_url}{path}"

            if method.upper() == "POST":
                resp = await self._client.post(url, content=xml_body, headers=headers, params=merged_params)
            else:
                resp = await self._client.get(url, headers=headers, params=merged_params)

            latency = int((time.monotonic() - start) * 1000)

            if resp.status_code == 401:
                return {"status": "fail", "latency_ms": latency, "error_code": "AUTH_INVALID", "message": "Kimlik bilgileri geçersiz (401)"}
            if resp.status_code == 403:
                return {"status": "fail", "latency_ms": latency, "error_code": "ACCESS_DENIED", "message": "Bu kaynak için erişim izni yok (403)"}
            if resp.status_code == 404:
                return {"status": "fail", "latency_ms": latency, "error_code": "NOT_FOUND", "message": "Kaynak bulunamadı. HR ID veya endpoint doğruluğunu kontrol edin (404)"}
            if resp.status_code == 429:
                return {"status": "warn", "latency_ms": latency, "error_code": "RATE_LIMITED", "message": "Rate limit aşıldı. Birkaç dakika sonra tekrar deneyin (429)"}
            if resp.status_code >= 500:
                return {"status": "fail", "latency_ms": latency, "error_code": "PROVIDER_ERROR", "message": f"HotelRunner sunucu hatası ({resp.status_code}). Lütfen daha sonra tekrar deneyin"}
            if resp.status_code >= 400:
                return {"status": "fail", "latency_ms": latency, "error_code": f"HTTP_{resp.status_code}", "message": f"Beklenmeyen hata ({resp.status_code})"}

            return {"status": "pass", "latency_ms": latency, "error_code": None, "message": "Başarılı"}

        except httpx.ConnectError:
            latency = int((time.monotonic() - start) * 1000)
            return {"status": "fail", "latency_ms": latency, "error_code": "CONN_REFUSED", "message": "HotelRunner API'sine bağlanılamıyor. Ağ bağlantınızı kontrol edin"}
        except httpx.TimeoutException:
            latency = int((time.monotonic() - start) * 1000)
            return {"status": "fail", "latency_ms": latency, "error_code": "TIMEOUT", "message": "Bağlantı zaman aşımına uğradı. Sunucu yanıt vermiyor"}
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            return {"status": "fail", "latency_ms": latency, "error_code": "UNKNOWN", "message": str(e)}

    async def test_connection_detailed(self) -> Dict[str, Any]:
        """
        Production-grade connection test that validates each integration layer separately.
        Returns a structured result with per-step status, latency, and actionable error messages.
        """
        from datetime import datetime, timezone as tz

        tested_at = datetime.now(tz.utc).isoformat()

        # Step 1: Authentication validity
        auth_result = await self._test_single_step(
            "authentication", "GET", "/properties",
        )

        # Step 2: Property / hotel access
        property_result = await self._test_single_step(
            "property_access", "GET", f"/hotels/{self._auth.hr_id}",
        )

        # Step 3: Room type fetch
        room_result = await self._test_single_step(
            "room_type_fetch", "GET", f"/hotels/{self._auth.hr_id}/rooms",
        )

        # Step 4: Rate plan fetch
        rate_result = await self._test_single_step(
            "rate_plan_fetch", "GET", f"/hotels/{self._auth.hr_id}/rate_plans",
        )

        # Step 5: XML API connectivity (OTA ReadRQ)
        from . import xml_builder
        read_xml = xml_builder.build_read_rq(hr_id=self._auth.hr_id)
        xml_result = await self._test_single_step(
            "xml_api", "POST", "/reservations/read", xml_body=read_xml,
        )

        # Aggregate latency
        steps = [auth_result, property_result, room_result, rate_result, xml_result]
        total_latency = sum(s["latency_ms"] for s in steps)
        failed_count = sum(1 for s in steps if s["status"] == "fail")
        warn_count = sum(1 for s in steps if s["status"] == "warn")

        overall_success = failed_count == 0

        return {
            "success": overall_success,
            "tested_at": tested_at,
            "total_latency_ms": total_latency,
            "summary": f"{5 - failed_count}/5 test başarılı" + (f", {warn_count} uyarı" if warn_count else ""),
            "auth_status": auth_result,
            "inventory_read_status": room_result,
            "rate_read_status": rate_result,
            "property_access_status": property_result,
            "xml_connectivity_status": xml_result,
        }

    async def test_connection(self) -> Dict[str, Any]:
        """Legacy simple test - delegates to detailed test."""
        return await self.test_connection_detailed()
