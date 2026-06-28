"""
Webhook Service - Handles incoming webhook/callback events from channel providers.

Security:
  - HMAC-SHA256 signature verification
  - Timestamp validation (max 5 min drift)
  - Rate limiting per connector

Flow:
  receive -> verify signature -> validate timestamp -> parse payload
  -> create domain event -> trigger reservation import / inventory sync
"""

import hashlib
import hmac
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.webhook_service")

MAX_TIMESTAMP_DRIFT_SECONDS = 300  # 5 minutes
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 60

# In-memory rate limiter (per connector)
_rate_limits: dict[str, list[float]] = {}


class WebhookService:
    """Processes incoming webhooks from channel providers."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def process_webhook(
        self,
        tenant_id: str,
        raw_body: bytes,
        signature: str | None,
        timestamp: str | None,
        provider: str = "hotelrunner",
        connector_id: str | None = None,
    ) -> dict[str, Any]:
        """Process an incoming webhook event with full security validation."""
        event_id = str(uuid.uuid4())
        received_at = datetime.now(UTC).isoformat()

        # Rate limiting
        rate_key = f"{tenant_id}:{provider}"
        if not self._check_rate_limit(rate_key):
            await self._store_webhook_event(tenant_id, event_id, provider, "rate_limited", received_at)
            await self._audit(
                tenant_id,
                "",
                "",
                AuditAction.WEBHOOK_FAILED,
                metadata={
                    "event_id": event_id,
                    "reason": "rate_limited",
                },
            )
            return {"accepted": False, "event_id": event_id, "reason": "rate_limited"}

        # Find connector
        connector = None
        if connector_id:
            connector = await self._repo.get_connector(tenant_id, connector_id)
        else:
            connectors = await self._repo.get_connectors_by_tenant(tenant_id)
            for c in connectors:
                if c.get("provider") == provider and c.get("status") == "active":
                    connector = c
                    connector_id = c["id"]
                    break

        if not connector:
            await self._store_webhook_event(tenant_id, event_id, provider, "no_connector", received_at)
            return {"accepted": False, "event_id": event_id, "reason": "no_active_connector"}

        property_id = connector.get("property_id", "")
        webhook_secret = connector.get("credentials", {}).get("webhook_secret", "")

        # ── v106 Bug DAD (architect adversarial #6): previously this method was
        # FAIL-OPEN — if webhook_secret was unset on the connector OR the caller
        # omitted the signature/timestamp headers, BOTH checks were silently
        # skipped and the webhook was accepted. An attacker who knew any active
        # tenant_id (which leaks via many endpoints) could forge reservation_*
        # webhooks at will: fake bookings, cancel real ones, corrupt inventory.
        # Now FAIL-CLOSED — signing is mandatory unless explicitly disabled in
        # dev via ALLOW_UNSIGNED_CM_WEBHOOK=1.
        import os as _os

        unsigned_ok = _os.environ.get("ALLOW_UNSIGNED_CM_WEBHOOK") == "1"

        if not webhook_secret:
            if not unsigned_ok:
                await self._store_webhook_event(
                    tenant_id,
                    event_id,
                    provider,
                    "secret_missing",
                    received_at,
                    connector_id=connector_id,
                )
                await self._audit(
                    tenant_id,
                    property_id,
                    connector_id,
                    AuditAction.WEBHOOK_SIGNATURE_INVALID,
                    metadata={"event_id": event_id, "reason": "no_webhook_secret_configured"},
                )
                return {"accepted": False, "event_id": event_id, "reason": "webhook_signing_not_configured"}
        else:
            if not signature or not timestamp:
                await self._store_webhook_event(
                    tenant_id,
                    event_id,
                    provider,
                    "signature_missing",
                    received_at,
                    connector_id=connector_id,
                )
                await self._audit(
                    tenant_id,
                    property_id,
                    connector_id,
                    AuditAction.WEBHOOK_SIGNATURE_INVALID,
                    metadata={"event_id": event_id, "reason": "missing_signature_or_timestamp"},
                )
                return {"accepted": False, "event_id": event_id, "reason": "missing_signature_headers"}
            # Validate timestamp BEFORE signature so an attacker cannot replay
            # an old (body, signature) pair with a fresh ts (signature is now
            # bound to ts via signed_payload = ts + "." + body — see
            # _verify_signature below).
            if not self._validate_timestamp(timestamp):
                await self._store_webhook_event(
                    tenant_id,
                    event_id,
                    provider,
                    "timestamp_expired",
                    received_at,
                    connector_id=connector_id,
                )
                return {"accepted": False, "event_id": event_id, "reason": "timestamp_expired"}
            if not self._verify_signature(raw_body, signature, webhook_secret, timestamp):
                await self._store_webhook_event(
                    tenant_id,
                    event_id,
                    provider,
                    "signature_invalid",
                    received_at,
                    connector_id=connector_id,
                )
                await self._audit(
                    tenant_id,
                    property_id,
                    connector_id,
                    AuditAction.WEBHOOK_SIGNATURE_INVALID,
                    metadata={"event_id": event_id},
                )
                return {"accepted": False, "event_id": event_id, "reason": "invalid_signature"}

        # Parse payload
        import json

        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError):
            await self._store_webhook_event(
                tenant_id,
                event_id,
                provider,
                "parse_error",
                received_at,
                connector_id=connector_id,
            )
            return {"accepted": False, "event_id": event_id, "reason": "invalid_json"}

        # Determine event type from payload
        event_type = payload.get("event_type", payload.get("type", "unknown"))
        webhook_data = payload.get("data", payload)

        # Store webhook event
        await self._store_webhook_event(
            tenant_id,
            event_id,
            provider,
            "accepted",
            received_at,
            connector_id=connector_id,
            event_type=event_type,
            payload=payload,
        )

        # Process based on event type
        actions_taken = []

        if event_type in ("reservation_created", "reservation_modified", "reservation_cancelled", "booking"):
            from ..application.reservation_import_service import ReservationImportService

            svc = ReservationImportService(self._repo)
            try:
                await svc.pull_and_import(
                    tenant_id=tenant_id,
                    connector_id=connector_id,
                    triggered_by="webhook",
                )
                actions_taken.append({"action": "reservation_import", "result": "success"})
            except Exception as e:
                logger.error("Webhook reservation import failed: %s", e)
                actions_taken.append({"action": "reservation_import", "result": "failed", "error": str(e)[:200]})

        if event_type in ("inventory_updated", "availability_changed", "room_status_changed"):
            from ..application.event_sync_service import EventSyncService

            svc = EventSyncService(self._repo)
            try:
                await svc.handle_event(
                    tenant_id,
                    "room_unblocked",
                    {
                        "property_id": property_id,
                        "date_start": webhook_data.get("date_start", datetime.now(UTC).strftime("%Y-%m-%d")),
                        "date_end": webhook_data.get("date_end", (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")),
                    },
                )
                actions_taken.append({"action": "inventory_sync", "result": "success"})
            except Exception as e:
                logger.error("Webhook inventory sync failed: %s", e)
                actions_taken.append({"action": "inventory_sync", "result": "failed", "error": str(e)[:200]})

        # Audit
        await self._audit(
            tenant_id,
            property_id,
            connector_id,
            AuditAction.WEBHOOK_RECEIVED,
            metadata={
                "event_id": event_id,
                "event_type": event_type,
                "actions_taken": len(actions_taken),
                "provider": provider,
            },
        )

        return {
            "accepted": True,
            "event_id": event_id,
            "event_type": event_type,
            "actions_taken": actions_taken,
            "processed_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _verify_signature(
        body: bytes,
        signature: str,
        secret: str,
        timestamp: str | None = None,
    ) -> bool:
        """Verify HMAC-SHA256 signature.

        v106 architect follow-up (Bug DAD): signature is now bound to the
        timestamp (signed_payload = "<ts>." + body) so a captured (body,
        signature) pair cannot be replayed by tampering only the ts header.
        Old behavior (body-only) is kept ONLY when caller passes no ts (i.e.
        legacy paths that explicitly opted out of replay protection).
        """
        if timestamp:
            signed_payload = f"{timestamp}.".encode() + body
        else:
            signed_payload = body
        expected = hmac.new(
            secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(
            expected,
            signature.replace("sha256=", "").lower(),
        )

    @staticmethod
    def _validate_timestamp(timestamp_str: str) -> bool:
        """Validate that the timestamp is within acceptable drift."""
        try:
            ts = int(timestamp_str)
            now = int(time.time())
            return abs(now - ts) <= MAX_TIMESTAMP_DRIFT_SECONDS
        except (ValueError, TypeError):
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                age = abs((datetime.now(UTC) - dt).total_seconds())
                return age <= MAX_TIMESTAMP_DRIFT_SECONDS
            except (ValueError, TypeError):
                return False

    @staticmethod
    def _check_rate_limit(key: str) -> bool:
        """Simple in-memory rate limiter."""
        now = time.time()
        if key not in _rate_limits:
            _rate_limits[key] = []
        _rate_limits[key] = [t for t in _rate_limits[key] if now - t < RATE_LIMIT_WINDOW_SECONDS]
        if len(_rate_limits[key]) >= RATE_LIMIT_MAX_REQUESTS:
            return False
        _rate_limits[key].append(now)
        return True

    async def _store_webhook_event(
        self,
        tenant_id,
        event_id,
        provider,
        status,
        received_at,
        connector_id=None,
        event_type=None,
        payload=None,
    ):
        doc = {
            "id": event_id,
            "tenant_id": tenant_id,
            "provider": provider,
            "connector_id": connector_id or "",
            "event_type": event_type or "",
            "status": status,
            "payload_summary": str(payload)[:500] if payload else "",
            "received_at": received_at,
        }
        await self._repo.store_webhook_event(doc)

    async def get_webhook_events(self, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return await self._repo.get_webhook_events(tenant_id, limit)

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            action=action,
            actor_id=actor_id,
            actor_type="webhook",
            metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
