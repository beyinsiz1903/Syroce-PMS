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

import httpx

from .errors import (
    ExelyAuthError,
    ExelyPayloadError,
    ExelyRateLimitError,
    ExelyTemporaryError,
)

logger = logging.getLogger("exely.client")

EXELY_DEFAULT_URL = "https://pmsconnect.test.hopenapi.com/api/PMSConnect.svc"
SOAP_CONTENT_TYPE = "text/xml; charset=utf-8"
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


class ExelySoapTransport:
    """
    Production-grade async SOAP transport for Exely API.

    All provider methods go through send_soap().
    Retry logic is handled externally by the provider layer.
    """

    def __init__(self, endpoint_url: str = EXELY_DEFAULT_URL):
        self._endpoint_url = endpoint_url

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
                    "[EXELY] SOAP egress blocked (SSRF guard): endpoint=%s reason=%s [%s]",
                    self._endpoint_url,
                    _e,
                    corr_id,
                )
                raise ExelyPayloadError(f"endpoint URL not permitted: {_e}") from _e

            duration_ms = int((time.monotonic() - start) * 1000)

            logger.info(
                "[EXELY] SOAP %s -> %d (%dms) [%s]",
                soap_action or "POST",
                resp.status_code,
                duration_ms,
                corr_id,
            )
            if "NotifReport" in (soap_action or "") or "ResNotif" in (soap_action or ""):
                logger.info("[EXELY] NOTIF REQUEST [%s]:\n%s", corr_id, xml_body[:3000])
                logger.info("[EXELY] NOTIF RESPONSE [%s]:\n%s", corr_id, resp.text[:3000])
            if "ReadReservation" in (soap_action or "") or "ResRetrieve" in (soap_action or ""):
                logger.info("[EXELY] READRQ RESPONSE [%s]:\n%s", corr_id, resp.text[:8000])
            logger.debug(
                "[EXELY] RAW REQUEST [%s]:\n%s",
                corr_id,
                xml_body[:2000],
            )
            logger.debug(
                "[EXELY] RAW RESPONSE [%s]:\n%s",
                corr_id,
                resp.text[:3000],
            )

            self._raise_for_http_status(resp, duration_ms, corr_id)
            return resp.content

        except (
            ExelyAuthError,
            ExelyRateLimitError,
            ExelyTemporaryError,
            ExelyPayloadError,
        ):
            raise
        except httpx.ConnectError:
            raise ExelyTemporaryError(f"Cannot connect to Exely SOAP API ({self._endpoint_url})")
        except httpx.TimeoutException:
            raise ExelyTemporaryError(f"Exely SOAP API timeout ({soap_action})")

    @staticmethod
    def _raise_for_http_status(resp: httpx.Response, duration_ms: int, corr_id: str) -> None:
        code = resp.status_code
        if 200 <= code < 300:
            return
        if code == 401 or code == 403:
            raise ExelyAuthError(f"HTTP {code} — authentication/access denied [{corr_id}]")
        if code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            raise ExelyRateLimitError(
                retry_after_seconds=retry_after,
                message=f"Rate limit exceeded ({code}) [{corr_id}]",
            )
        if code == 400:
            raise ExelyPayloadError(f"Bad request ({code}) [{corr_id}]: {resp.text[:500]}")
        if code >= 500:
            raise ExelyTemporaryError(f"Server error ({code}) [{corr_id}]")
        if code >= 400:
            raise ExelyPayloadError(f"Client error ({code}) [{corr_id}]: {resp.text[:500]}")
