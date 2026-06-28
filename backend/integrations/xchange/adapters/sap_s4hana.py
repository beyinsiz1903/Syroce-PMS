"""SAP S/4HANA Finance adapter (OData V4 + OAuth2).

Translates canonical Posting / NightAuditClose messages into a SAP
Journal Entry payload (`API_JOURNALENTRYITEMBULKCREATE`-compatible).
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from ..safety import EgressDenied, safe_post_async
from ..schemas import MessageType, XchangeEnvelope
from .base import BaseAdapter, DeliveryResult

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class SapS4HanaAdapter(BaseAdapter):
    code = "sap_s4hana"

    @property
    def is_dry_run(self) -> bool:
        c = self.config
        return not (c.get("base_url") and c.get("client_id") and c.get("client_secret") and c.get("token_url"))

    async def _get_token(self) -> str:
        c = self.config
        cache_key = f"{c['client_id']}@{c['token_url']}"
        cached = _TOKEN_CACHE.get(cache_key)
        if cached and cached[1] > time.time() + 30:
            return cached[0]
        # v109 Bug DAL round-7 follow-up #2: token_url is tenant-configurable
        # — use rebinding-safe transport. Caller (deliver) catches EgressDenied
        # via the egress_denied error path.
        resp = await safe_post_async(
            c["token_url"],
            data={"grant_type": "client_credentials"},
            auth=(c["client_id"], c.get("client_secret", "")),
        )
        resp.raise_for_status()
        data = resp.json()
        tok = data["access_token"]
        ttl = int(data.get("expires_in", 3600))
        _TOKEN_CACHE[cache_key] = (tok, time.time() + ttl)
        return tok

    def _build_journal(self, envelope: XchangeEnvelope) -> dict:
        c = self.config
        p = envelope.payload
        company = c.get("company_code", "1000")
        ledger = c.get("ledger", "0L")

        if envelope.message_type == MessageType.NIGHT_AUDIT_CLOSE:
            lines = []
            for i, jl in enumerate(p.get("journal_lines", []), start=1):
                lines.append(
                    {
                        "GLAccount": jl.get("gl_account", "0000400000"),
                        "AmountInTransactionCurrency": float(jl.get("amount", 0)),
                        "TransactionCurrency": p.get("currency", "TRY"),
                        "DebitCreditCode": jl.get("dc", "S"),  # S=Debit, H=Credit
                        "DocumentItemText": jl.get("description", "")[:50],
                        "PostingKey": jl.get("posting_key", "40"),
                        "ItemNumber": i,
                    }
                )
            return {
                "CompanyCode": company,
                "Ledger": ledger,
                "DocumentDate": str(p["business_date"]),
                "PostingDate": str(p["business_date"]),
                "DocumentReferenceID": f"NA-{p['business_date']}",
                "DocumentHeaderText": "Syroce Night Audit",
                "TransactionCurrency": p.get("currency", "TRY"),
                "JournalEntryItemBulk": lines,
            }

        # Single posting (charge/payment)
        return {
            "CompanyCode": company,
            "Ledger": ledger,
            "DocumentDate": p["posted_at"][:10] if isinstance(p.get("posted_at"), str) else str(p["posted_at"])[:10],
            "PostingDate": p["posted_at"][:10] if isinstance(p.get("posted_at"), str) else str(p["posted_at"])[:10],
            "DocumentReferenceID": p["posting_id"],
            "DocumentHeaderText": (p.get("description", ""))[:25],
            "TransactionCurrency": p.get("currency", "TRY"),
            "JournalEntryItemBulk": [
                {
                    "GLAccount": "0000400000" if p["posting_type"] == "CHARGE" else "0000100000",
                    "AmountInTransactionCurrency": float(p["amount"]),
                    "TransactionCurrency": p.get("currency", "TRY"),
                    "DebitCreditCode": "S" if p["posting_type"] == "CHARGE" else "H",
                    "DocumentItemText": p.get("description", "")[:50],
                    "PostingKey": "40" if p["posting_type"] == "CHARGE" else "50",
                    "ItemNumber": 1,
                }
            ],
        }

    async def deliver(self, envelope: XchangeEnvelope) -> DeliveryResult:
        body = self._build_journal(envelope)
        excerpt = json.dumps(body, indent=2, default=str)[:1024]

        if self.is_dry_run:
            logger.info("[sap_s4hana] DRY-RUN %s tenant=%s", envelope.message_type.value, envelope.tenant_id)
            return DeliveryResult(
                ok=True,
                dry_run=True,
                request_payload_excerpt=excerpt,
                response_excerpt="DRY-RUN: no SAP credentials configured",
            )

        # v109 Bug DAL round-7 follow-up #2: both token_url and base_url are
        # tenant-configurable; safe_post_async (called inside _get_token and
        # below) validates all resolved IPs and pins the TCP destination,
        # closing the rebinding window. EgressDenied surfaces here as the
        # egress_denied error path for both endpoints.
        try:
            token = await self._get_token()
        except EgressDenied as e:
            return DeliveryResult(ok=False, error=f"egress_denied: {e}", request_payload_excerpt=excerpt)
        except Exception as e:
            return DeliveryResult(ok=False, error=f"oauth_failed: {e!r}", request_payload_excerpt=excerpt)

        url = self.config["base_url"].rstrip("/") + "/API_JOURNALENTRYITEMBULKCREATE"
        try:
            resp = await safe_post_async(
                url,
                timeout=20.0,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Idempotency-Key": envelope.message_id,
                },
            )
        except EgressDenied as e:
            return DeliveryResult(ok=False, error=f"egress_denied: {e}", request_payload_excerpt=excerpt)
        except httpx.RequestError as e:
            return DeliveryResult(ok=False, error=f"transport_error: {e!r}", request_payload_excerpt=excerpt)
        ok = 200 <= resp.status_code < 300
        return DeliveryResult(
            ok=ok,
            status_code=resp.status_code,
            request_payload_excerpt=excerpt,
            response_excerpt=resp.text[:1024],
            error=None if ok else f"HTTP {resp.status_code}",
        )
