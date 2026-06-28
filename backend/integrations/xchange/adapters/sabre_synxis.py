"""Sabre SynXis (HTNG 2024B over HTTPS) adapter."""

from __future__ import annotations

import logging

import httpx

from ..htng import serialize
from ..safety import EgressDenied, safe_post_async
from ..schemas import XchangeEnvelope
from .base import BaseAdapter, DeliveryResult

logger = logging.getLogger(__name__)


class SabreSynXisAdapter(BaseAdapter):
    code = "sabre_synxis"

    @property
    def is_dry_run(self) -> bool:
        # Require ALL essential credentials before attempting live calls.
        c = self.config
        return not (c.get("endpoint") and c.get("username") and c.get("password") and c.get("hotel_code"))

    async def deliver(self, envelope: XchangeEnvelope) -> DeliveryResult:
        xml = serialize(envelope)
        excerpt = xml[:1024]

        if self.is_dry_run:
            logger.info("[sabre_synxis] DRY-RUN %s tenant=%s msg=%s", envelope.message_type.value, envelope.tenant_id, envelope.message_id)
            return DeliveryResult(
                ok=True,
                dry_run=True,
                request_payload_excerpt=excerpt,
                response_excerpt="DRY-RUN: no SynXis credentials configured",
            )

        headers = {
            "Content-Type": "application/xml; charset=utf-8",
            "SOAPAction": envelope.message_type.value,
            "X-Hotel-Code": str(self.config.get("hotel_code", "")),
            "X-EchoToken": envelope.message_id,
        }
        # v109 Bug DAL round-7 follow-up #2: safe_post_async pins DNS to a
        # validated IP, closing the rebinding window between validation and
        # the actual TCP connect. Tenant-configurable endpoint URL.
        try:
            resp = await safe_post_async(
                self.config["endpoint"],
                timeout=20.0,
                content=xml.encode("utf-8"),
                headers=headers,
                auth=(self.config["username"], self.config.get("password", "")),
            )
        except EgressDenied as e:
            return DeliveryResult(ok=False, error=f"egress_denied: {e}", request_payload_excerpt=excerpt)
        except httpx.RequestError as e:
            return DeliveryResult(
                ok=False,
                error=f"transport_error: {e!r}",
                request_payload_excerpt=excerpt,
            )
        ok = 200 <= resp.status_code < 300
        return DeliveryResult(
            ok=ok,
            status_code=resp.status_code,
            request_payload_excerpt=excerpt,
            response_excerpt=resp.text[:1024],
            error=None if ok else f"HTTP {resp.status_code}",
        )
