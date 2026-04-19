"""Generic HMAC-signed JSON webhook adapter (Zapier/Make/n8n compatible)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx

from ..safety import EgressDenied, assert_safe_url
from ..schemas import XchangeEnvelope
from .base import BaseAdapter, DeliveryResult

logger = logging.getLogger(__name__)


class GenericWebhookAdapter(BaseAdapter):
    code = "generic_webhook"

    @property
    def is_dry_run(self) -> bool:
        return not self.config.get("url")

    async def deliver(self, envelope: XchangeEnvelope) -> DeliveryResult:
        body = json.dumps({
            "message_id": envelope.message_id,
            "message_type": envelope.message_type.value,
            "tenant_id": envelope.tenant_id,
            "occurred_at": envelope.occurred_at.isoformat(),
            "correlation_id": envelope.correlation_id,
            "payload": envelope.payload,
        }, default=str).encode("utf-8")
        excerpt = body.decode("utf-8")[:1024]

        if self.is_dry_run:
            logger.info("[generic_webhook] DRY-RUN msg=%s", envelope.message_id)
            return DeliveryResult(
                ok=True, dry_run=True,
                request_payload_excerpt=excerpt,
                response_excerpt="DRY-RUN: no webhook URL configured",
            )

        try:
            assert_safe_url(self.config["url"])
        except EgressDenied as e:
            return DeliveryResult(ok=False, error=f"egress_denied: {e}",
                                  request_payload_excerpt=excerpt)
        secret = (self.config.get("secret") or "").encode("utf-8")
        sig = hmac.new(secret, body, hashlib.sha256).hexdigest() if secret else ""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    self.config["url"],
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Syroce-Signature": f"sha256={sig}",
                        "X-Syroce-Message-Id": envelope.message_id,
                        "X-Syroce-Message-Type": envelope.message_type.value,
                    },
                )
            ok = 200 <= resp.status_code < 300
            return DeliveryResult(
                ok=ok,
                status_code=resp.status_code,
                request_payload_excerpt=excerpt,
                response_excerpt=resp.text[:1024],
                error=None if ok else f"HTTP {resp.status_code}",
            )
        except httpx.RequestError as e:
            return DeliveryResult(ok=False, error=f"transport_error: {e!r}",
                                  request_payload_excerpt=excerpt)
