"""
Exely Provider — SOAP HTTP Client
====================================

Low-level SOAP HTTP transport. ONLY module that makes network calls.

Responsibilities:
- Build and send SOAP envelopes
- Enforce timeouts (connect: 5s, read: 30s)
- Map HTTP status codes and SOAP Faults to typed errors
- Log every request with correlation context
"""

import logging
import time
import uuid as _uuid
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from .errors import (
    ExelyAuthError,
    ExelyPayloadError,
    ExelyRateLimitError,
    ExelyTemporaryError,
)
from .security import EXELY_TEST_ENDPOINT_URL, safe_fingerprint, validate_exely_endpoint

logger = logging.getLogger("exely.client")

EXELY_DEFAULT_URL = EXELY_TEST_ENDPOINT_URL
SOAP_CONTENT_TYPE = "text/xml; charset=utf-8"
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_DEFAULT_RETRY_AFTER_SECONDS = 60
_MAX_RETRY_AFTER_SECONDS = 3600


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> int:
    """Parse seconds or an HTTP-date without trusting unbounded provider input."""
    candidate = str(value or "").strip()
    seconds = _DEFAULT_RETRY_AFTER_SECONDS
    if candidate.isdigit():
        seconds = int(candidate)
    elif candidate:
        try:
            parsed = parsedate_to_datetime(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            seconds = int((parsed - (now or datetime.now(UTC))).total_seconds())
        except (TypeError, ValueError, OverflowError):
            seconds = _DEFAULT_RETRY_AFTER_SECONDS
    return max(1, min(seconds, _MAX_RETRY_AFTER_SECONDS))


class ExelySoapTransport:
    """
    Production-grade async SOAP transport for Exely API.

    All provider methods go through send_soap().
    Retry logic is handled externally by the provider layer.
    """

    def __init__(self, endpoint_url: str = EXELY_DEFAULT_URL):
        self._endpoint_url = validate_exely_endpoint(endpoint_url)

    async def send_soap(
        self,
        xml_body: str,
        soap_action: str = "",
        *,
        correlation_id: str = "",
    ) -> bytes:
        """
        Send SOAP request and return raw response bytes.
        Raises typed errors for HTTP and SOAP failures.
        """
        corr_id = correlation_id or str(_uuid.uuid4())[:12]
        corr_tag = safe_fingerprint(corr_id)
        operation = (soap_action or "SOAP").rsplit("/", 1)[-1]
        headers = {
            "Content-Type": SOAP_CONTENT_TYPE,
            "SOAPAction": soap_action,
        }
        start = time.monotonic()

        # v109 Bug DAL round-7 (T12 SSRF + rebinding follow-up): tenant admins
        # set endpoint_url via connector setup ("Test Connection" /
        # provisioning flow). ``safe_post_async`` validates scheme + every
        # resolved IP, then pins the TCP connection to the validated IP so
        # the host can't rebind to 169.254.169.254 / loopback / RFC 1918
        # between validation and the actual SOAP POST.
        from integrations.xchange.safety import EgressDenied, safe_post_async

        try:
            try:
                resp = await safe_post_async(
                    self._endpoint_url,
                    timeout=_TIMEOUT,
                    content=xml_body.encode("utf-8"),
                    headers=headers,
                )
            except EgressDenied as _e:
                logger.warning(
                    "[EXELY] egress_blocked operation=%s exception_class=%s corr=%s",
                    operation,
                    type(_e).__name__,
                    corr_tag,
                )
                raise ExelyPayloadError("Exely endpoint egress denied") from _e

            duration_ms = int((time.monotonic() - start) * 1000)

            logger.info(
                "[EXELY] operation=%s status_class=%dxx duration_ms=%d corr=%s",
                operation,
                resp.status_code // 100,
                duration_ms,
                corr_tag,
            )

            self._raise_for_http_status(resp, duration_ms, corr_tag)
            return resp.content

        except (
            ExelyAuthError,
            ExelyRateLimitError,
            ExelyTemporaryError,
            ExelyPayloadError,
        ):
            raise
        except httpx.ConnectError:
            raise ExelyTemporaryError("Cannot connect to Exely SOAP API")
        except httpx.TimeoutException:
            raise ExelyTemporaryError(f"Exely SOAP API timeout ({operation})")
        except httpx.RequestError:
            raise ExelyTemporaryError(f"Exely SOAP API transport error ({operation})")

    @staticmethod
    def _raise_for_http_status(resp: httpx.Response, duration_ms: int, corr_id: str) -> None:
        code = resp.status_code
        if 200 <= code < 300:
            return
        if code == 401 or code == 403:
            raise ExelyAuthError(f"HTTP {code} — authentication/access denied [{corr_id}]")
        if code == 429:
            retry_after = parse_retry_after(resp.headers.get("Retry-After"))
            raise ExelyRateLimitError(
                retry_after_seconds=retry_after,
                message=f"Rate limit exceeded ({code}) [{corr_id}]",
            )
        if code == 400:
            raise ExelyPayloadError(f"Bad request ({code}) [{corr_id}]")
        if code >= 500:
            raise ExelyTemporaryError(f"Server error ({code}) [{corr_id}]")
        if code >= 400:
            raise ExelyPayloadError(f"Client error ({code}) [{corr_id}]")
