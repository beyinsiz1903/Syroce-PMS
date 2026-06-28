"""
HotelRunner HTTP Client — Production connector.

Supports both XML/OTA endpoints (inventory, rates) and REST/JSON endpoints (reservations).
"""

import logging
import time
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from . import xml_builder, xml_parser
from .auth import HotelRunnerAuth
from .connector_errors import (
    AcknowledgementError,
    AuthenticationError,
    ConnectorError,
    PaginationExhaustedError,
    ProviderUnavailableError,
    RateLimitError,
    ResponseParseError,
)
from .rate_limit import RateLimiter
from .retry_policy import RetryPolicy

logger = logging.getLogger("channel_manager.hotelrunner.client")

HOTELRUNNER_API_BASE = "https://app.hotelrunner.com/api/v2"
HOTELRUNNER_SANDBOX_BASE = "https://sandbox.hotelrunner.com/api/v2"
HOTELRUNNER_MOCK_BASE = "http://localhost:9999/api/v2"

# Safety limits
MAX_PAGINATION_PAGES = 100
DEFAULT_PER_PAGE = 50
AUDIT_TRUNCATE_LEN = 4000
MASK_KEYS = {"token", "password", "secret", "api_key"}

# Environment config
VALID_ENVIRONMENTS = ("mock", "sandbox", "production")


def _mask_params(params: dict[str, str]) -> dict[str, str]:
    """Mask sensitive query parameters for audit logs."""
    masked = {}
    for k, v in params.items():
        if k.lower() in MASK_KEYS:
            masked[k] = f"{v[:4]}****" if len(v) > 4 else "****"
        else:
            masked[k] = v
    return masked


def _truncate(text: str, max_len: int = AUDIT_TRUNCATE_LEN) -> str:
    """Truncate text for audit storage."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [truncated, total {len(text)} chars]"


class HotelRunnerClient:
    """
    Production-grade async HTTP client for HotelRunner API.

    Features:
      - Token-based authentication (token + hr_id query params)
      - REST/JSON for reservations, XML/OTA for inventory/rates
      - Paginated reservation retrieval
      - Confirm delivery acknowledgement
      - Rate limiting (token bucket)
      - Automatic retry with exponential backoff
      - Raw request/response audit with correlation_id, masking, truncation
    """

    def __init__(
        self,
        auth: HotelRunnerAuth,
        sandbox: bool = True,
        environment: str = "sandbox",
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
    ):
        self._auth = auth
        # Environment-based URL selection
        if environment == "production":
            self._base_url = HOTELRUNNER_API_BASE
        elif environment == "mock":
            self._base_url = HOTELRUNNER_MOCK_BASE
        else:
            self._base_url = HOTELRUNNER_SANDBOX_BASE
        self._environment = environment
        self._rate_limiter = rate_limiter or RateLimiter()
        self._retry_policy = retry_policy or RetryPolicy()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        self._sandbox = sandbox or environment == "sandbox"
        self._audit_entries: list[dict[str, Any]] = []

    async def close(self):
        await self._client.aclose()

    @property
    def audit_entries(self) -> list[dict[str, Any]]:
        """Return collected audit entries from this session."""
        return list(self._audit_entries)

    def clear_audit(self):
        self._audit_entries.clear()

    # ─── XML/OTA Request (inventory, rates) ──────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        xml_body: str | None = None,
        params: dict[str, str] | None = None,
    ) -> str:
        """Make an authenticated XML request to HotelRunner API."""
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
                    url,
                    content=xml_body,
                    headers=headers,
                    params=merged_params,
                )
            else:
                response = await self._client.get(
                    url,
                    headers=headers,
                    params=merged_params,
                )

            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "HR XML %s %s -> %d (%dms)",
                method,
                path,
                response.status_code,
                duration_ms,
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

    # ─── REST/JSON Request (reservations) ────────────────────────────

    async def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        correlation_id: str | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        """
        Make an authenticated REST/JSON request to HotelRunner API.
        Returns (parsed_json, audit_entry).
        """
        acquired = await self._rate_limiter.acquire(timeout=120)
        if not acquired:
            raise RateLimitError(retry_after_seconds=60, message="Local rate limit exceeded")

        corr_id = correlation_id or str(_uuid.uuid4())
        url = f"{self._base_url}{path}"
        merged_params = {**(params or {}), **self._auth.get_auth_params()}
        headers = {
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }

        audit = {
            "correlation_id": corr_id,
            "method": method.upper(),
            "url": f"{self._base_url}{path}",
            "params": _mask_params(merged_params),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        start = time.monotonic()
        try:
            if method.upper() == "PUT":
                response = await self._client.put(
                    url,
                    params=merged_params,
                    headers=headers,
                )
            elif method.upper() == "POST":
                response = await self._client.post(
                    url,
                    params=merged_params,
                    headers=headers,
                )
            else:
                response = await self._client.get(
                    url,
                    params=merged_params,
                    headers=headers,
                )

            duration_ms = int((time.monotonic() - start) * 1000)
            audit["latency_ms"] = duration_ms
            audit["status_code"] = response.status_code
            audit["response_body"] = _truncate(response.text)

            logger.info(
                "HR REST %s %s -> %d (%dms)",
                method,
                path,
                response.status_code,
                duration_ms,
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

            try:
                data = response.json()
            except Exception as e:
                raise ResponseParseError(
                    f"Invalid JSON response: {e}",
                    raw_response=response.text[:2000],
                )

            self._audit_entries.append(audit)
            return data, audit

        except (AuthenticationError, RateLimitError, ProviderUnavailableError, ConnectorError, ResponseParseError):
            audit["latency_ms"] = int((time.monotonic() - start) * 1000)
            self._audit_entries.append(audit)
            raise
        except httpx.ConnectError:
            audit["latency_ms"] = int((time.monotonic() - start) * 1000)
            audit["error"] = "connection_refused"
            self._audit_entries.append(audit)
            raise ProviderUnavailableError("Cannot connect to HotelRunner API")
        except httpx.TimeoutException:
            audit["latency_ms"] = int((time.monotonic() - start) * 1000)
            audit["error"] = "timeout"
            self._audit_entries.append(audit)
            raise ProviderUnavailableError("HotelRunner API request timed out")

    # ─── Inventory / Rates (XML) ─────────────────────────────────────

    async def push_availability(
        self,
        updates: list,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Push inventory availability to HotelRunner.

        Returns: {success: bool, errors: [], warnings: [], correlation_id, latency_ms, raw_request_len, raw_response_len}
        """
        corr_id = correlation_id or str(_uuid.uuid4())
        xml_body = xml_builder.build_availability_notif(
            hr_id=self._auth.hr_id,
            updates=updates,
        )

        audit = {
            "correlation_id": corr_id,
            "operation": "push_availability",
            "environment": self._environment,
            "timestamp": datetime.now(UTC).isoformat(),
            "request_payload_len": len(xml_body),
            "update_count": len(updates),
        }
        start = time.monotonic()

        async def _do():
            resp_xml = await self._request("POST", "/ari/availability", xml_body=xml_body)
            return resp_xml

        try:
            resp_xml = await self._retry_policy.execute_with_retry(_do)
            latency_ms = int((time.monotonic() - start) * 1000)
            result = xml_parser.parse_response_status(resp_xml)
            audit["latency_ms"] = latency_ms
            audit["response_payload_len"] = len(resp_xml)
            audit["success"] = result.get("success", False)
            self._audit_entries.append(audit)

            result["correlation_id"] = corr_id
            result["latency_ms"] = latency_ms
            result["raw_request_len"] = len(xml_body)
            result["raw_response_len"] = len(resp_xml)
            return result

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            audit["latency_ms"] = latency_ms
            audit["error"] = str(e)[:500]
            audit["error_type"] = type(e).__name__
            audit["success"] = False
            self._audit_entries.append(audit)
            raise

    async def push_rates(
        self,
        updates: list,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Push rate amounts to HotelRunner.

        Returns: {success: bool, errors: [], warnings: [], correlation_id, latency_ms}
        """
        corr_id = correlation_id or str(_uuid.uuid4())
        xml_body = xml_builder.build_rate_amount_notif(
            hr_id=self._auth.hr_id,
            updates=updates,
        )

        audit = {
            "correlation_id": corr_id,
            "operation": "push_rates",
            "environment": self._environment,
            "timestamp": datetime.now(UTC).isoformat(),
            "request_payload_len": len(xml_body),
            "update_count": len(updates),
        }
        start = time.monotonic()

        async def _do():
            resp_xml = await self._request("POST", "/ari/rates", xml_body=xml_body)
            return resp_xml

        try:
            resp_xml = await self._retry_policy.execute_with_retry(_do)
            latency_ms = int((time.monotonic() - start) * 1000)
            result = xml_parser.parse_response_status(resp_xml)
            audit["latency_ms"] = latency_ms
            audit["response_payload_len"] = len(resp_xml)
            audit["success"] = result.get("success", False)
            self._audit_entries.append(audit)

            result["correlation_id"] = corr_id
            result["latency_ms"] = latency_ms
            result["raw_request_len"] = len(xml_body)
            result["raw_response_len"] = len(resp_xml)
            return result

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            audit["latency_ms"] = latency_ms
            audit["error"] = str(e)[:500]
            audit["error_type"] = type(e).__name__
            audit["success"] = False
            self._audit_entries.append(audit)
            raise

    # ─── Reservations (REST/JSON) ────────────────────────────────────

    async def pull_reservations(
        self,
        date_start: str | None = None,
        date_end: str | None = None,
        per_page: int = DEFAULT_PER_PAGE,
        undelivered: bool = True,
        modified_only: bool = False,
        booked_only: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Pull reservations from HotelRunner REST/JSON endpoint with pagination.

        GET /api/v2/apps/reservations
        Auth: token + hr_id as query params
        Returns: list of raw reservation JSON dicts
        """
        all_reservations: list[dict[str, Any]] = []
        page = 1
        corr_id = str(_uuid.uuid4())

        async def _do_page(pg: int) -> tuple[list[dict], int]:
            params: dict[str, str] = {
                "per_page": str(per_page),
            }
            if undelivered:
                params["undelivered"] = "true"
            else:
                params["undelivered"] = "false"
                params["page"] = str(pg)

            if modified_only:
                params["modified"] = "true"
            if booked_only:
                params["booked"] = "true"
            if date_start:
                params["from_date"] = date_start
            if date_end:
                params["from_last_update_date"] = date_end

            data, _ = await self._request_json(
                "GET",
                "/apps/reservations",
                params=params,
                correlation_id=f"{corr_id}-page-{pg}",
            )

            reservations = data.get("reservations", [])
            total_pages = data.get("pages", 1)
            return reservations, total_pages

        # First page with retry
        async def _first():
            return await _do_page(1)

        page_data, total_pages = await self._retry_policy.execute_with_retry(_first)
        all_reservations.extend(page_data)

        if not undelivered and total_pages > 1:
            # Paginate through remaining pages
            for page in range(2, min(total_pages + 1, MAX_PAGINATION_PAGES + 1)):

                async def _next(p=page):
                    return await _do_page(p)

                next_data, _ = await self._retry_policy.execute_with_retry(_next)
                if not next_data:
                    break
                all_reservations.extend(next_data)

            if total_pages > MAX_PAGINATION_PAGES:
                logger.warning(
                    "Pagination safety limit reached: %d/%d pages fetched",
                    MAX_PAGINATION_PAGES,
                    total_pages,
                )
                raise PaginationExhaustedError(MAX_PAGINATION_PAGES, len(all_reservations))

        logger.info(
            "Pulled %d reservations across %d pages (corr=%s)",
            len(all_reservations),
            min(total_pages, MAX_PAGINATION_PAGES),
            corr_id,
        )
        return all_reservations

    async def acknowledge_reservation(
        self,
        message_uid: str,
        pms_number: str | None = None,
    ) -> dict[str, Any]:
        """
        Confirm delivery of a single reservation to HotelRunner.

        PUT /api/v2/apps/reservations/~
        Params: token, hr_id, message_uid, pms_number (optional)
        Returns: {"status": "ok"} on success
        """
        params: dict[str, str] = {"message_uid": message_uid}
        if pms_number:
            params["pms_number"] = pms_number

        corr_id = str(_uuid.uuid4())

        async def _do():
            data, _ = await self._request_json(
                "PUT",
                "/apps/reservations/~",
                params=params,
                correlation_id=corr_id,
            )
            if data.get("status") != "ok":
                raise AcknowledgementError(
                    message_uid=message_uid,
                    reason=data.get("message", "Unknown error"),
                )
            return data

        return await self._retry_policy.execute_with_retry(_do)

    async def acknowledge_reservations(
        self,
        ack_items: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Confirm delivery of multiple reservations.

        Each item: {"message_uid": str, "pms_number": Optional[str]}
        Returns: {"sent": int, "failed": int, "errors": list}
        """
        results = {"sent": 0, "failed": 0, "errors": []}

        for item in ack_items:
            msg_uid = item.get("message_uid", "")
            pms_num = item.get("pms_number")
            if not msg_uid:
                results["failed"] += 1
                results["errors"].append({"message_uid": "", "error": "Empty message_uid"})
                continue
            try:
                await self.acknowledge_reservation(msg_uid, pms_num)
                results["sent"] += 1
            except (ConnectorError, AcknowledgementError) as e:
                results["failed"] += 1
                results["errors"].append(
                    {
                        "message_uid": msg_uid,
                        "error": str(e),
                    }
                )
                logger.warning("ACK failed for uid=%s: %s", msg_uid, e)

        return results

    async def update_reservation_state(
        self,
        hr_number: str,
        event: str,
        cancel_reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Update reservation state (confirm/cancel) on HotelRunner.
        Only valid when requires_response=true.

        PUT /api/v2/apps/reservations/fire
        Params: hr_number, event (confirm|cancel), cancel_reason
        """
        params: dict[str, str] = {
            "hr_number": hr_number,
            "event": event,
        }
        if event == "cancel" and cancel_reason:
            params["cancel_reason"] = cancel_reason

        corr_id = str(_uuid.uuid4())

        async def _do():
            data, _ = await self._request_json(
                "PUT",
                "/apps/reservations/fire",
                params=params,
                correlation_id=corr_id,
            )
            if data.get("status") == "error":
                raise ConnectorError(
                    f"State update failed: {data.get('message', 'unknown')}",
                    recoverable=False,
                )
            return data

        return await self._retry_policy.execute_with_retry(_do)

    # ─── Connection Test ─────────────────────────────────────────────

    async def _test_single_step(self, step_name: str, method: str, path: str, xml_body: str | None = None) -> dict[str, Any]:
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
                return {"status": "fail", "latency_ms": latency, "error_code": "AUTH_INVALID", "message": "Invalid credentials (401)"}
            if resp.status_code == 403:
                return {"status": "fail", "latency_ms": latency, "error_code": "ACCESS_DENIED", "message": "Access denied for this resource (403)"}
            if resp.status_code == 404:
                return {"status": "fail", "latency_ms": latency, "error_code": "NOT_FOUND", "message": "Resource not found. Check HR ID or endpoint (404)"}
            if resp.status_code == 429:
                return {"status": "warn", "latency_ms": latency, "error_code": "RATE_LIMITED", "message": "Rate limit exceeded. Please try again in a few minutes (429)"}
            if resp.status_code >= 500:
                return {"status": "fail", "latency_ms": latency, "error_code": "PROVIDER_ERROR", "message": f"HotelRunner server error ({resp.status_code}). Please try again later"}
            if resp.status_code >= 400:
                return {"status": "fail", "latency_ms": latency, "error_code": f"HTTP_{resp.status_code}", "message": f"Unexpected error ({resp.status_code})"}

            return {"status": "pass", "latency_ms": latency, "error_code": None, "message": "Success"}

        except httpx.ConnectError:
            latency = int((time.monotonic() - start) * 1000)
            return {"status": "fail", "latency_ms": latency, "error_code": "CONN_REFUSED", "message": "Cannot connect to HotelRunner API. Check your network connection"}
        except httpx.TimeoutException:
            latency = int((time.monotonic() - start) * 1000)
            return {"status": "fail", "latency_ms": latency, "error_code": "TIMEOUT", "message": "Connection timed out. Server is not responding"}
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            return {"status": "fail", "latency_ms": latency, "error_code": "UNKNOWN", "message": str(e)}

    async def test_connection_detailed(self) -> dict[str, Any]:
        """
        Production-grade connection test that validates each integration layer separately.
        Returns a structured result with per-step status, latency, and actionable error messages.
        """
        tested_at = datetime.now(UTC).isoformat()

        # Step 1: Authentication validity
        auth_result = await self._test_single_step(
            "authentication",
            "GET",
            "/properties",
        )

        # Step 2: Property / hotel access
        property_result = await self._test_single_step(
            "property_access",
            "GET",
            f"/hotels/{self._auth.hr_id}",
        )

        # Step 3: Room type fetch
        room_result = await self._test_single_step(
            "room_type_fetch",
            "GET",
            f"/hotels/{self._auth.hr_id}/rooms",
        )

        # Step 4: Rate plan fetch
        rate_result = await self._test_single_step(
            "rate_plan_fetch",
            "GET",
            f"/hotels/{self._auth.hr_id}/rate_plans",
        )

        # Step 5: REST reservation endpoint (JSON)
        rest_result = await self._test_single_step(
            "rest_reservations",
            "GET",
            "/apps/reservations",
        )

        steps = [auth_result, property_result, room_result, rate_result, rest_result]
        total_latency = sum(s["latency_ms"] for s in steps)
        failed_count = sum(1 for s in steps if s["status"] == "fail")
        warn_count = sum(1 for s in steps if s["status"] == "warn")

        overall_success = failed_count == 0

        return {
            "success": overall_success,
            "tested_at": tested_at,
            "total_latency_ms": total_latency,
            "summary": f"{5 - failed_count}/5 tests passed" + (f", {warn_count} warning(s)" if warn_count else ""),
            "auth_status": auth_result,
            "inventory_read_status": room_result,
            "rate_read_status": rate_result,
            "property_access_status": property_result,
            "xml_connectivity_status": rest_result,
        }

    async def test_connection(self) -> dict[str, Any]:
        """Legacy simple test - delegates to detailed test."""
        return await self.test_connection_detailed()
