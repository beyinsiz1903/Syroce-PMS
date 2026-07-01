"""
Delta Push Runtime Loop — Background Worker with Observability
===============================================================

Continuously processes pending ARI change sets:
  buffer → coalesce → hard_fail gate → compile → rate_limit → push → ack

Observability metrics:
  - queued_changes:        Total changes waiting to be pushed
  - coalesced_changes:     Changes merged during coalescing
  - dropped_as_duplicate:  Changes skipped (outbound idempotency)
  - hard_fail_blocked:     Changes blocked by mapping gate
  - emitted_payloads:      Successful pushes to providers
  - verify_success_count:  Successful ack responses
  - verify_fail_count:     Failed ack responses
  - provider_ack_latency:  Average ack latency per provider (ms)
  - cycle_count:           Total push cycles executed
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from domains.channel_manager.ari import repositories as repo
from domains.channel_manager.ari.ack_service import process_ack
from domains.channel_manager.ari.delta_compiler import compile_delta
from domains.channel_manager.ari.events import ProviderResult
from domains.channel_manager.ari.hard_fail_gate import (
    HF_PASS,
    enforce_hard_fail_gate,
)
from domains.channel_manager.ari.rate_limit_service import rate_limiter

logger = logging.getLogger("ari.push_loop")


class PushLoopMetrics:
    """Thread-safe push loop metrics collector."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.queued_changes: int = 0
        self.coalesced_changes: int = 0
        self.dropped_as_duplicate: int = 0
        self.hard_fail_blocked: int = 0
        self.emitted_payloads: int = 0
        self.verify_success_count: int = 0
        self.verify_fail_count: int = 0
        self.cycle_count: int = 0
        self.last_cycle_at: str | None = None
        self.last_cycle_duration_ms: int = 0
        self._provider_latencies: dict[str, list[int]] = defaultdict(list)

    def record_ack_latency(self, provider: str, latency_ms: int):
        self._provider_latencies[provider].append(latency_ms)
        # Keep only last 100 samples per provider
        if len(self._provider_latencies[provider]) > 100:
            self._provider_latencies[provider] = self._provider_latencies[provider][-100:]

    def get_avg_latency(self, provider: str) -> float:
        samples = self._provider_latencies.get(provider, [])
        return round(sum(samples) / len(samples), 1) if samples else 0.0

    def to_dict(self) -> dict[str, Any]:
        provider_latency = {p: self.get_avg_latency(p) for p in self._provider_latencies}
        total_verify = self.verify_success_count + self.verify_fail_count
        return {
            "queued_changes": self.queued_changes,
            "coalesced_changes": self.coalesced_changes,
            "dropped_as_duplicate": self.dropped_as_duplicate,
            "hard_fail_blocked": self.hard_fail_blocked,
            "emitted_payloads": self.emitted_payloads,
            "verify_success_count": self.verify_success_count,
            "verify_fail_count": self.verify_fail_count,
            "verify_success_ratio": (round(self.verify_success_count / total_verify, 3) if total_verify > 0 else 0.0),
            "cycle_count": self.cycle_count,
            "last_cycle_at": self.last_cycle_at,
            "last_cycle_duration_ms": self.last_cycle_duration_ms,
            "provider_ack_latency_avg_ms": provider_latency,
        }


class PushLoopWorker:
    """
    Background push loop worker.

    Periodically polls for pending change sets and pushes them
    through the full pipeline with hard-fail gating.
    """

    def __init__(self, interval_seconds: float = 5.0, batch_size: int = 50):
        self._interval = interval_seconds
        self._batch_size = batch_size
        self._running = False
        self._paused = False
        self._task: asyncio.Task | None = None
        self.metrics = PushLoopMetrics()
        self._provider_adapters: dict[str, object] = {}
        self._started_at: str | None = None

    def register_adapter(self, provider: str, adapter):
        self._provider_adapters[provider] = adapter

    @property
    def status(self) -> str:
        if not self._running:
            return "stopped"
        if self._paused:
            return "paused"
        return "running"

    async def start(self):
        if self._running:
            return
        self._running = True
        self._paused = False
        self._started_at = datetime.now(UTC).isoformat()
        self._task = asyncio.create_task(self._loop())
        logger.info("Push loop worker started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Push loop worker stopped")

    def pause(self):
        self._paused = True
        logger.info("Push loop worker paused")

    def resume(self):
        self._paused = False
        logger.info("Push loop worker resumed")

    async def _loop(self):
        while self._running:
            try:
                if self._paused:
                    await asyncio.sleep(1)
                    continue

                cycle_start = time.monotonic()
                await self._process_cycle()
                cycle_ms = int((time.monotonic() - cycle_start) * 1000)

                self.metrics.cycle_count += 1
                self.metrics.last_cycle_at = datetime.now(UTC).isoformat()
                self.metrics.last_cycle_duration_ms = cycle_ms

                await asyncio.sleep(self._interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Push loop error: {e}")
                await asyncio.sleep(self._interval * 2)

    async def _process_cycle(self):
        """Process one batch of pending change sets across all tenants."""
        from core.database import db
        from domains.channel_manager.ari.models import COLL_ARI_CHANGE_SETS

        # Find distinct tenants with pending work
        tenants = await db[COLL_ARI_CHANGE_SETS].distinct(
            "tenant_id",
            {"status": {"$in": ["pending", "failed_retryable"]}},
        )

        for tenant_id in tenants:
            await self._process_tenant(tenant_id)

    async def _process_tenant(self, tenant_id: str):
        """Process pending change sets for a single tenant."""
        pending = await repo.get_pending_change_sets(
            tenant_id,
            limit=self._batch_size,
        )
        self.metrics.queued_changes = len(pending)

        for cs in pending:
            provider = cs["provider"]
            property_id = cs["property_id"]

            # 1. Hard fail gate
            verdict = await enforce_hard_fail_gate(cs)
            if verdict.status != HF_PASS:
                self.metrics.hard_fail_blocked += 1
                continue

            # 2. Outbound idempotency check
            is_dupe = await repo.check_outbound_idempotency(
                provider,
                property_id,
                cs["provider_delta_hash"],
            )
            if is_dupe:
                await repo.update_change_set_status(cs["id"], "skipped")
                self.metrics.dropped_as_duplicate += 1
                continue

            # 3. Rate limit check
            allowed = await rate_limiter.acquire(provider, property_id)
            if not allowed:
                continue

            # 4. Compile delta
            try:
                delta = compile_delta(cs)
            except Exception as e:
                logger.error(f"Delta compile error: {e}")
                await repo.update_change_set_status(
                    cs["id"],
                    "manual_review",
                    error=str(e),
                )
                self.metrics.verify_fail_count += 1
                continue

            # 5. Mark as pushed
            await repo.update_change_set_status(cs["id"], "pushed", inc_attempt=True)

            # 6. Push to provider
            adapter = self._provider_adapters.get(provider)
            if not adapter:
                # No adapter = can't push (this is OK in dev, logged)
                await repo.update_change_set_status(
                    cs["id"],
                    "pending",
                    error="No adapter registered (waiting for provider setup)",
                )
                continue

            push_start = time.monotonic()
            try:
                result = await self._push_to_adapter(adapter, delta)
            except Exception as e:
                result = ProviderResult(
                    success=False,
                    provider=provider,
                    error=str(e),
                    retryable=True,
                )
            push_ms = int((time.monotonic() - push_start) * 1000)

            # Record latency
            self.metrics.record_ack_latency(provider, push_ms)

            # Handle 429
            if result.status_code == 429:
                rate_limiter.record_429(provider, property_id)

            # 7. Process ack
            status = await process_ack(
                cs,
                result,
                cs.get("outbound_change_id", ""),
            )

            if status == "acked":
                self.metrics.emitted_payloads += 1
                self.metrics.verify_success_count += 1
            else:
                self.metrics.verify_fail_count += 1

    async def _push_to_adapter(self, adapter, delta) -> ProviderResult:
        scope = delta.change_scope
        if scope == "availability":
            return await adapter.push_availability(delta)
        elif scope == "rate":
            return await adapter.push_rate(delta)
        elif scope == "restriction":
            return await adapter.push_restrictions(delta)
        return ProviderResult(
            success=False,
            provider=delta.provider,
            error=f"Unknown scope: {scope}",
        )

    def get_status(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self._started_at,
            "interval_seconds": self._interval,
            "batch_size": self._batch_size,
            "registered_adapters": list(self._provider_adapters.keys()),
            "metrics": self.metrics.to_dict(),
        }


# Singleton worker
_push_worker: PushLoopWorker | None = None


def get_push_worker() -> PushLoopWorker:
    global _push_worker
    if _push_worker is None:
        _push_worker = PushLoopWorker()
    return _push_worker
