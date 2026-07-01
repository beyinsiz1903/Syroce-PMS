"""Syroce Xchange message bus.

Persists every outbound envelope as a delivery record in MongoDB,
dispatches to all enabled partner adapters for the tenant, retries
transient failures with exponential backoff and parks unrecoverable
messages in a dead-letter state for manual replay.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from core.tenant_db import get_system_db
from core.transient_db_guard import TransientFailureTracker

from .adapters.base import BaseAdapter, DeliveryResult
from .registry import PARTNERS, get_partner
from .schemas import (
    DeliveryStatus,
    Direction,
    MessageType,
    XchangeEnvelope,
)

_xchange_retry_tracker = TransientFailureTracker("xchange-retry")

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [30, 120, 600, 3600]  # seconds — 30s, 2m, 10m, 1h
_MAX_ATTEMPTS = 5


class XchangeBus:
    """Single bus instance — lazy DB resolution to stay test-friendly."""

    def __init__(self):
        self._adapter_cache: dict[str, BaseAdapter] = {}
        self._indexes_ready = False

    @property
    def db(self):
        return get_system_db()

    async def ensure_indexes(self) -> None:
        """Idempotent index creation — call once at app startup or first use."""
        if self._indexes_ready:
            return
        try:
            await self.db.xchange_deliveries.create_index(
                [("tenant_id", ASCENDING), ("message_id", ASCENDING), ("partner_code", ASCENDING)],
                unique=True,
                name="uniq_tenant_msg_partner",
            )
            await self.db.xchange_deliveries.create_index(
                [("status", ASCENDING), ("next_attempt_at", ASCENDING)],
                name="retry_scan",
            )
            await self.db.xchange_partner_configs.create_index(
                [("tenant_id", ASCENDING), ("partner_code", ASCENDING)],
                unique=True,
                name="uniq_tenant_partner",
            )
            self._indexes_ready = True
        except Exception as e:
            logger.warning("[xchange] index ensure failed: %s", e)

    # ── Partner config ─────────────────────────────────────────
    async def get_tenant_partner_configs(self, tenant_id: str) -> list[dict[str, Any]]:
        cur = self.db.xchange_partner_configs.find({"tenant_id": tenant_id, "enabled": True})
        return [doc async for doc in cur]

    async def upsert_partner_config(
        self,
        tenant_id: str,
        partner_code: str,
        *,
        config: dict[str, Any],
        enabled: bool = True,
    ) -> dict[str, Any]:
        if partner_code not in PARTNERS:
            raise ValueError(f"Unknown partner: {partner_code}")
        doc = {
            "tenant_id": tenant_id,
            "partner_code": partner_code,
            "enabled": enabled,
            "config": config,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await self.db.xchange_partner_configs.update_one(
            {"tenant_id": tenant_id, "partner_code": partner_code},
            {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"]}},
            upsert=True,
        )
        return doc

    def _build_adapter(self, partner_code: str, config: dict[str, Any]) -> BaseAdapter:
        cache_key = f"{partner_code}:{id(config)}"
        if cache_key in self._adapter_cache:
            return self._adapter_cache[cache_key]
        partner = get_partner(partner_code)
        if not partner:
            raise ValueError(f"Unknown partner: {partner_code}")
        module = importlib.import_module(partner.adapter_module)
        # Convention: each adapter file exports a *Adapter class
        adapter_cls = next(
            (v for k, v in vars(module).items() if isinstance(v, type) and k.endswith("Adapter") and k != "BaseAdapter"),
            None,
        )
        if not adapter_cls:
            raise RuntimeError(f"Adapter class not found in {partner.adapter_module}")
        adapter = adapter_cls(config)
        self._adapter_cache[cache_key] = adapter
        return adapter

    # ── Delivery records ───────────────────────────────────────
    async def _record(self, envelope: XchangeEnvelope, partner_code: str, status: DeliveryStatus, *, result: DeliveryResult | None = None) -> str:
        delivery_id = str(uuid.uuid4())
        doc = {
            "id": delivery_id,
            "tenant_id": envelope.tenant_id,
            "message_id": envelope.message_id,
            "message_type": envelope.message_type.value,
            "direction": envelope.direction.value,
            "partner_code": partner_code,
            "status": status.value,
            "occurred_at": envelope.occurred_at.isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
            "attempts": 0,
            "next_attempt_at": None,
            "last_error": None,
            "request_excerpt": None,
            "response_excerpt": None,
            "dry_run": False,
            "envelope": envelope.model_dump(mode="json"),
        }
        if result:
            doc.update(
                {
                    "request_excerpt": result.request_payload_excerpt,
                    "response_excerpt": result.response_excerpt,
                    "dry_run": result.dry_run,
                    "last_error": result.error,
                    "attempts": 1,
                }
            )
        await self.db.xchange_deliveries.insert_one(doc)
        return delivery_id

    async def _update_delivery(self, delivery_id: str, **patch) -> None:
        patch["updated_at"] = datetime.now(UTC).isoformat()
        await self.db.xchange_deliveries.update_one({"id": delivery_id}, {"$set": patch})

    # ── Public publish API ─────────────────────────────────────
    async def publish(
        self,
        *,
        tenant_id: str,
        message_type: MessageType,
        payload: dict[str, Any],
        correlation_id: str | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """Build an envelope and dispatch to all enabled partners.

        Idempotency: callers may pass a stable message_id (e.g. the
        reservation ID + revision); duplicate envelopes for the same
        (tenant, message_id, partner) tuple are deduplicated.
        """
        envelope = XchangeEnvelope(
            message_id=message_id or str(uuid.uuid4()),
            message_type=message_type,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            occurred_at=datetime.now(UTC),
            payload=payload,
            direction=Direction.OUTBOUND,
        )

        partner_configs = await self.get_tenant_partner_configs(tenant_id)
        results: list[dict[str, Any]] = []

        for pc in partner_configs:
            partner_code = pc["partner_code"]
            partner_def = get_partner(partner_code)
            if not partner_def:
                continue

            # Filter by capability
            supports = any(c.message_type == message_type and c.direction == Direction.OUTBOUND for c in partner_def.capabilities)
            if not supports:
                results.append({"partner": partner_code, "skipped": "capability_unsupported"})
                continue

            # Atomic idempotency: insert a PENDING claim row first; the
            # unique index on (tenant_id, message_id, partner_code) makes
            # this safe under concurrent publishers.
            await self.ensure_indexes()
            delivery_id = str(uuid.uuid4())
            claim = {
                "id": delivery_id,
                "tenant_id": envelope.tenant_id,
                "message_id": envelope.message_id,
                "message_type": envelope.message_type.value,
                "direction": envelope.direction.value,
                "partner_code": partner_code,
                "status": DeliveryStatus.IN_FLIGHT.value,
                "occurred_at": envelope.occurred_at.isoformat(),
                "created_at": datetime.now(UTC).isoformat(),
                "attempts": 0,
                "next_attempt_at": None,
                "last_error": None,
                "request_excerpt": None,
                "response_excerpt": None,
                "dry_run": False,
                "envelope": envelope.model_dump(mode="json"),
            }
            try:
                await self.db.xchange_deliveries.insert_one(claim)
            except DuplicateKeyError:
                existing = await self.db.xchange_deliveries.find_one(
                    {
                        "tenant_id": envelope.tenant_id,
                        "message_id": envelope.message_id,
                        "partner_code": partner_code,
                    },
                    {"id": 1},
                )
                results.append({"partner": partner_code, "skipped": "duplicate", "delivery_id": (existing or {}).get("id")})
                continue

            try:
                adapter = self._build_adapter(partner_code, pc.get("config") or {})
                result = await adapter.deliver(envelope)
            except Exception as e:
                result = DeliveryResult(ok=False, error=f"adapter_exception: {e!r}")

            status = DeliveryStatus.DELIVERED if result.ok else DeliveryStatus.FAILED
            await self._update_delivery(
                delivery_id,
                status=status.value,
                attempts=1,
                request_excerpt=result.request_payload_excerpt,
                response_excerpt=result.response_excerpt,
                last_error=result.error,
                dry_run=result.dry_run,
            )

            # Schedule retry if failed and not dry-run
            if not result.ok and not result.dry_run:
                await self._update_delivery(
                    delivery_id,
                    next_attempt_at=(datetime.now(UTC) + timedelta(seconds=_RETRY_DELAYS[0])).isoformat(),
                )

            results.append(
                {
                    "partner": partner_code,
                    "delivery_id": delivery_id,
                    "ok": result.ok,
                    "dry_run": result.dry_run,
                    "error": result.error,
                }
            )

        return {
            "message_id": envelope.message_id,
            "tenant_id": tenant_id,
            "type": message_type.value,
            "deliveries": results,
        }

    # ── Retry / replay ─────────────────────────────────────────
    async def replay_delivery(self, delivery_id: str) -> dict[str, Any]:
        doc = await self.db.xchange_deliveries.find_one({"id": delivery_id})
        if not doc:
            raise ValueError("delivery not found")
        env_data = doc.get("envelope", {})
        if "message_type" in env_data and isinstance(env_data["message_type"], str):
            env_data["message_type"] = MessageType(env_data["message_type"])
        if "direction" in env_data and isinstance(env_data["direction"], str):
            env_data["direction"] = Direction(env_data["direction"])
        envelope = XchangeEnvelope(**env_data)
        partner_code = doc["partner_code"]
        pc = await self.db.xchange_partner_configs.find_one({"tenant_id": envelope.tenant_id, "partner_code": partner_code})
        if not pc:
            raise ValueError("partner not configured")
        try:
            adapter = self._build_adapter(partner_code, pc.get("config") or {})
            result = await adapter.deliver(envelope)
        except Exception as e:
            result = DeliveryResult(ok=False, error=f"adapter_exception: {e!r}")
        attempts = int(doc.get("attempts", 0)) + 1
        next_status = DeliveryStatus.DELIVERED if result.ok else (DeliveryStatus.DEAD_LETTER if attempts >= _MAX_ATTEMPTS else DeliveryStatus.FAILED)
        next_attempt = None
        if next_status == DeliveryStatus.FAILED:
            delay = _RETRY_DELAYS[min(attempts - 1, len(_RETRY_DELAYS) - 1)]
            next_attempt = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
        await self._update_delivery(
            delivery_id,
            status=next_status.value,
            attempts=attempts,
            request_excerpt=result.request_payload_excerpt,
            response_excerpt=result.response_excerpt,
            last_error=result.error,
            dry_run=result.dry_run,
            next_attempt_at=next_attempt,
        )
        return {
            "delivery_id": delivery_id,
            "ok": result.ok,
            "attempts": attempts,
            "status": next_status.value,
            "error": result.error,
        }

    # ── Background retry worker ────────────────────────────────
    async def run_retry_cycle(self, *, batch: int = 25) -> int:
        """Scan for due retries, dispatch them, advance to DLQ as needed.

        Returns the number of deliveries processed in this cycle.
        Safe to call repeatedly from a periodic task.
        """
        await self.ensure_indexes()
        now_iso = datetime.now(UTC).isoformat()
        cur = self.db.xchange_deliveries.find(
            {
                "status": DeliveryStatus.FAILED.value,
                "next_attempt_at": {"$lte": now_iso},
            }
        ).limit(batch)
        processed = 0
        async for doc in cur:
            # Atomically claim by clearing next_attempt_at
            claimed = await self.db.xchange_deliveries.find_one_and_update(
                {"id": doc["id"], "status": DeliveryStatus.FAILED.value, "next_attempt_at": doc.get("next_attempt_at")},
                {"$set": {"status": DeliveryStatus.IN_FLIGHT.value, "next_attempt_at": None}},
            )
            if not claimed:
                continue
            try:
                await self.replay_delivery(doc["id"])
            except Exception as e:
                logger.warning("[xchange] retry %s failed: %s", doc["id"], e)
                await self._update_delivery(
                    doc["id"],
                    status=DeliveryStatus.FAILED.value,
                    last_error=f"worker_error: {e!r}",
                )
            processed += 1
        return processed

    async def start_retry_loop(self, *, interval_seconds: int = 30) -> None:
        """Long-running task — schedule via app startup if desired."""
        logger.info("[xchange] retry loop started (interval=%ds)", interval_seconds)
        while True:
            try:
                count = await self.run_retry_cycle()
                if count:
                    logger.info("[xchange] retry cycle processed %d", count)
                _xchange_retry_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
            except Exception as e:
                _xchange_retry_tracker.log_exception(
                    logger,
                    e,
                    TransientFailureTracker.OUTER_LOOP_KEY,
                    context="retry loop tick",
                    non_transient_msg="%s retry loop error: %s",
                )
            await asyncio.sleep(interval_seconds)


bus = XchangeBus()
