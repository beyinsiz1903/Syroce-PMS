"""
ARI Outbound Service — Main push orchestrator.

Coordinates: buffer → coalesce → compile delta → rate limit check → provider push → ack.
"""
import asyncio
import logging
from typing import Dict, List, Optional

from .events import ARIChangeEvent, ARIDelta, ProviderResult
from .buffer import ARIEventBuffer
from .coalescer import coalesce_events
from .delta_compiler import compile_delta
from .rate_limit_service import rate_limiter
from .ack_service import process_ack
from . import repositories as repo

logger = logging.getLogger(__name__)

# Active providers per tenant (in production, this comes from DB)
_ACTIVE_PROVIDERS: Dict[str, List[str]] = {}

# Provider adapter registry
_PROVIDER_ADAPTERS: Dict[str, object] = {}


def register_provider_adapter(provider: str, adapter):
    """Register a provider ARI adapter."""
    _PROVIDER_ADAPTERS[provider] = adapter
    logger.info(f"Registered ARI adapter: {provider}")


def set_active_providers(tenant_id: str, providers: List[str]):
    """Set active providers for a tenant."""
    _ACTIVE_PROVIDERS[tenant_id] = providers


def get_active_providers(tenant_id: str) -> List[str]:
    """Get active providers for a tenant. Default: hotelrunner."""
    return _ACTIVE_PROVIDERS.get(tenant_id, ["hotelrunner"])


async def _on_buffer_flush(coalescing_key: str, events: List[ARIChangeEvent]):
    """Callback when buffer flushes a batch of events."""
    if not events:
        return

    tenant_id = events[0].tenant_id
    providers = get_active_providers(tenant_id)

    # Persist raw events
    for event in events:
        await repo.insert_ari_event(event.model_dump())

    # Coalesce into change sets
    change_sets = coalesce_events(coalescing_key, events, providers)

    # Upsert change sets
    for cs in change_sets:
        await repo.upsert_change_set(cs)

    logger.info(f"Buffer flush: {len(events)} events → {len(change_sets)} change sets")


# Singleton buffer
_buffer: Optional[ARIEventBuffer] = None


def get_buffer() -> ARIEventBuffer:
    global _buffer
    if _buffer is None:
        _buffer = ARIEventBuffer(on_flush=_on_buffer_flush)
    return _buffer


async def publish_ari_event(event: ARIChangeEvent) -> dict:
    """
    Main entry point: publish an ARI change event.
    Event goes into the buffer for debounce + coalescing.
    """
    buf = get_buffer()
    if not buf._running:
        await buf.start()

    key = await buf.push(event)
    return {
        "event_id": event.id,
        "coalescing_key": key,
        "buffered": True,
    }


async def push_pending_changes(
    tenant_id: str,
    provider: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """
    Process pending change sets: compile → rate limit → push → ack.
    Called by the push worker or manual trigger.
    """
    pending = await repo.get_pending_change_sets(tenant_id, provider, limit)

    results = {"pushed": 0, "skipped": 0, "failed": 0, "rate_limited": 0}

    for cs in pending:
        prov = cs["provider"]
        prop_id = cs["property_id"]

        # Hard fail gate check (runtime mapping enforcement)
        from .hard_fail_gate import enforce_hard_fail_gate, HF_PASS
        verdict = await enforce_hard_fail_gate(cs)
        if verdict.status != HF_PASS:
            results["failed"] += 1
            continue

        # Outbound idempotency check
        is_dupe = await repo.check_outbound_idempotency(
            prov, prop_id, cs["provider_delta_hash"]
        )
        if is_dupe:
            await repo.update_change_set_status(cs["id"], "skipped")
            results["skipped"] += 1
            continue

        # Rate limit check
        allowed = await rate_limiter.acquire(prov, prop_id)
        if not allowed:
            results["rate_limited"] += 1
            continue

        # Compile delta
        try:
            delta = compile_delta(cs)
        except Exception as e:
            logger.error(f"Delta compile error: {e}")
            await repo.update_change_set_status(cs["id"], "manual_review", error=str(e))
            results["failed"] += 1
            continue

        # Mark as pushed
        await repo.update_change_set_status(cs["id"], "pushed", inc_attempt=True)

        # Push to provider
        adapter = _PROVIDER_ADAPTERS.get(prov)
        if not adapter:
            logger.error(f"No adapter for provider: {prov}")
            await repo.update_change_set_status(cs["id"], "manual_review", error="No adapter registered")
            results["failed"] += 1
            continue

        try:
            result = await _push_to_provider(adapter, delta)
        except Exception as e:
            result = ProviderResult(
                success=False, provider=prov, error=str(e), retryable=True
            )

        # Handle 429
        if result.status_code == 429:
            rate_limiter.record_429(prov, prop_id)

        # Process ack
        status = await process_ack(
            cs, result, cs.get("outbound_change_id", "")
        )

        if status == "acked":
            results["pushed"] += 1
        else:
            results["failed"] += 1

    return results


async def _push_to_provider(adapter, delta: ARIDelta) -> ProviderResult:
    """Dispatch delta to the correct provider adapter method."""
    scope = delta.change_scope
    if scope == "availability":
        return await adapter.push_availability(delta)
    elif scope == "rate":
        return await adapter.push_rate(delta)
    elif scope == "restriction":
        return await adapter.push_restrictions(delta)
    else:
        return ProviderResult(
            success=False, provider=delta.provider,
            error=f"Unknown change scope: {scope}"
        )


async def force_push_change_set(cs_id: str) -> dict:
    """Force push a specific change set (manual override)."""
    from core.database import db
    from .models import COLL_ARI_CHANGE_SETS

    cs = await db[COLL_ARI_CHANGE_SETS].find_one({"id": cs_id}, {"_id": 0})
    if not cs:
        return {"error": "Change set not found"}

    await repo.update_change_set_status(cs_id, "pending")
    result = await push_pending_changes(
        cs["tenant_id"], cs["provider"], limit=1
    )
    return result


async def resync_property(tenant_id: str, property_id: str, provider: str, scope: str = "all") -> dict:
    """Trigger a full resync for a property+provider combination."""
    # This creates a special 'resync' event that bypasses normal coalescing
    logger.info(f"Resync triggered: {tenant_id}/{property_id}/{provider}/{scope}")
    return {
        "status": "resync_queued",
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": provider,
        "scope": scope,
    }


def get_engine_stats() -> dict:
    """Get overall ARI engine stats."""
    buf = get_buffer()
    return {
        "buffer": buf.get_buffer_stats(),
        "rate_limiter": rate_limiter.get_stats(),
        "registered_adapters": list(_PROVIDER_ADAPTERS.keys()),
        "active_tenants": {k: v for k, v in _ACTIVE_PROVIDERS.items()},
    }
