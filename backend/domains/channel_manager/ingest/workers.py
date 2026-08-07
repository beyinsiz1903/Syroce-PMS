"""
Reservation Ingest — Background Workers
========================================

Worker 1: HotelRunner Pull   (5-15 min interval)
Worker 2: Exely Pull          (5-10 min interval)
Worker 3: Ingest Processor    (processes pending raw events)
Worker 4: Replay Worker       (retries failed events)
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    ConnectorProvider,
    ProcessingStatus,
    RawChannelEvent,
    RawEventSource,
)
from domains.channel_manager.ingest.normalizer import (
    extract_exely_identity,
    extract_hotelrunner_identity,
)
from domains.channel_manager.ingest.pipeline import process_event

logger = logging.getLogger("ingest.workers")

# ── Worker State ──────────────────────────────────────────────────────

_worker_state = {
    "hotelrunner_pull": {
        "running": False,
        "last_run": None,
        "last_cursor": None,
        "interval_seconds": 600,  # 10 min default
        "events_fetched": 0,
        "errors": 0,
    },
    "exely_pull": {
        "running": False,
        "last_run": None,
        "last_cursor": None,
        "interval_seconds": 300,  # 5 min default
        "events_fetched": 0,
        "errors": 0,
    },
    "ingest_processor": {
        "running": False,
        "last_run": None,
        "interval_seconds": 10,  # 10 sec
        "events_processed": 0,
        "errors": 0,
    },
    "replay_worker": {
        "running": False,
        "last_run": None,
        "interval_seconds": 300,  # 5 min
        "events_replayed": 0,
        "errors": 0,
    },
}

SAFETY_WINDOW_MINUTES = 5


def get_worker_states() -> dict[str, Any]:
    return {k: {**v} for k, v in _worker_state.items()}


# ══════════════════════════════════════════════════════════════════════
# Worker 1: HotelRunner Pull
# ══════════════════════════════════════════════════════════════════════


async def hotelrunner_pull_once() -> dict[str, Any]:
    """
    Pull reservations from HotelRunner REST API for all active connections.
    Fetches updated reservations since last cursor, persists into raw_channel_events.
    """
    from domains.channel_manager.data_model import COLL_PROVIDER_CONNECTIONS
    from domains.channel_manager.providers.hotelrunner.factory import (
        get_provider as get_hotelrunner_provider,
    )

    state = _worker_state["hotelrunner_pull"]
    if state["running"]:
        return {"fetched": 0, "errors": 0, "provider": "hotelrunner", "status": "already_running"}
    state["running"] = True
    now = datetime.now(UTC)
    result = {"fetched": 0, "errors": 0, "provider": "hotelrunner"}

    try:
        last_cursor = state["last_cursor"]
        if last_cursor:
            updated_since = last_cursor - timedelta(minutes=SAFETY_WINDOW_MINUTES)
        else:
            updated_since = now - timedelta(hours=24)

        since_str = updated_since.strftime("%Y-%m-%d")

        connections = (
            await db[COLL_PROVIDER_CONNECTIONS]
            .find(
                {"provider": "hotelrunner", "status": "active", "sync_reservations": True},
                {"_id": 0},
            )
            .to_list(50)
        )

        if not connections:
            connections = (
                await db[COLL_PROVIDER_CONNECTIONS]
                .find(
                    {"provider": "hotelrunner"},
                    {"_id": 0},
                )
                .to_list(50)
            )

        for conn in connections:
            tenant_id = conn.get("tenant_id", "")
            property_id = conn.get("property_id", "")
            connection_id = conn.get("id", "")

            if not tenant_id:
                result["errors"] += 1
                logger.error("HotelRunner pull: tenant_id missing")
                continue

            try:
                provider, resolved_conn = await get_hotelrunner_provider(tenant_id)

                property_id = resolved_conn.get("property_id") or property_id
                connection_id = resolved_conn.get("id") or connection_id
                page = 1
                fetched_events = []

                while page <= 20:
                    api_result = await provider.get_reservations(
                        undelivered=True,
                        from_last_update_date=since_str,
                        per_page=50,
                        page=page,
                    )
                    if not api_result.get("success"):
                        logger.error(f"HotelRunner API error: {api_result.get('error')}")
                        result["errors"] += 1
                        break

                    data = api_result.get("data", {})
                    reservations = data.get("reservations", [])
                    fetched_events.extend(reservations)

                    if page >= data.get("pages", 1):
                        break
                    page += 1

                if fetched_events:
                    count = await _persist_pull_events(
                        "hotelrunner",
                        fetched_events,
                        tenant_id,
                        property_id,
                        connection_id,
                    )
                    result["fetched"] += count
                    state["events_fetched"] += count

                logger.info(f"HotelRunner pull [{property_id}]: fetched {len(fetched_events)} reservations")
            except Exception as e:
                result["errors"] += 1
                logger.error(f"HotelRunner pull error for {property_id}: {e}")

        state["last_cursor"] = now
        state["last_run"] = now.isoformat()

    except Exception as e:
        state["errors"] += 1
        result["errors"] += 1
        result["error_message"] = str(e)
        logger.error(f"HotelRunner pull error: {e}")
    finally:
        state["running"] = False

    return result


async def _persist_pull_events(
    provider: str,
    events: list[dict[str, Any]],
    tenant_id: str,
    property_id: str,
    connection_id: str = "",
) -> int:
    """Persist pulled events into raw_channel_events."""
    count = 0
    for payload in events:
        if provider == "hotelrunner":
            identity = extract_hotelrunner_identity(payload)
            event_type = "reservation_pull"
        else:
            identity = extract_exely_identity(payload)
            event_type = "reservation_pull"

        payload_hash = RawChannelEvent.compute_payload_hash(payload)

        event = RawChannelEvent(
            tenant_id=tenant_id,
            property_id=property_id,
            provider=ConnectorProvider(provider),
            connection_id=connection_id,
            event_type=event_type,
            provider_event_id=identity["provider_event_id"],
            external_reservation_id=identity["external_reservation_id"],
            provider_version=identity["provider_version"],
            provider_last_modified_at=identity["provider_last_modified_at"],
            raw_payload=payload,
            payload_hash=payload_hash,
            received_via=RawEventSource.PULL,
            processing_status=ProcessingStatus.PENDING,
        )
        await repo.insert_raw_event(event.to_doc())
        count += 1

    return count


# ══════════════════════════════════════════════════════════════════════
# Worker 2: Exely Pull
# ══════════════════════════════════════════════════════════════════════


async def exely_pull_once() -> dict[str, Any]:
    """Fail closed: Exely pulls are owned by ExelyPullScheduler only."""
    return {
        "fetched": 0,
        "errors": 1,
        "provider": "exely",
        "status": "disabled",
        "reason": "USE_CANONICAL_EXELY_PULL",
        "provider_write_count": 0,
    }


# ══════════════════════════════════════════════════════════════════════
# Worker 3: Ingest Processor
# ══════════════════════════════════════════════════════════════════════


async def ingest_processor_once(batch_size: int = 50) -> dict[str, Any]:
    """
    Process pending raw events through the ingest pipeline.
    """
    state = _worker_state["ingest_processor"]
    state["running"] = True
    now = datetime.now(UTC)
    result = {
        "processed": 0,
        "created": 0,
        "updated": 0,
        "cancelled": 0,
        "skipped": 0,
        "failed": 0,
        "pending_mapping": 0,
        "manual_review": 0,
    }

    try:
        pending = await repo.get_pending_raw_events(limit=batch_size)
        for event in pending:
            pipeline_result = await process_event(event)
            result["processed"] += 1
            decision = pipeline_result.decision
            if decision == "create":
                result["created"] += 1
            elif decision == "update":
                result["updated"] += 1
            elif decision == "cancel":
                result["cancelled"] += 1
            elif decision == "skip":
                result["skipped"] += 1
            elif decision == "pending_mapping":
                result["pending_mapping"] += 1
                result["failed"] += 1
            elif decision == "manual_review":
                result["manual_review"] += 1
                result["failed"] += 1

        state["events_processed"] += result["processed"]
        state["last_run"] = now.isoformat()
        logger.info(f"Ingest processor: {result}")

    except Exception as e:
        state["errors"] += 1
        result["error"] = str(e)
        logger.error(f"Ingest processor error: {e}")
    finally:
        state["running"] = False

    return result


# ══════════════════════════════════════════════════════════════════════
# Worker 4: Replay Worker
# ══════════════════════════════════════════════════════════════════════


async def replay_worker_once(batch_size: int = 20) -> dict[str, Any]:
    """
    Retry failed events by resetting their status to pending.
    """
    state = _worker_state["replay_worker"]
    state["running"] = True
    now = datetime.now(UTC)
    result = {"replayed": 0, "errors": 0}

    try:
        failed = await repo.get_failed_events(limit=batch_size)
        for event in failed:
            # Reset to pending for reprocessing
            await repo.update_raw_event_status(event["id"], "pending")
            result["replayed"] += 1

        state["events_replayed"] += result["replayed"]
        state["last_run"] = now.isoformat()
        logger.info(f"Replay worker: replayed {result['replayed']} events")

    except Exception as e:
        state["errors"] += 1
        result["errors"] = 1
        logger.error(f"Replay worker error: {e}")
    finally:
        state["running"] = False

    return result


# ══════════════════════════════════════════════════════════════════════
# Manual Trigger API helpers
# ══════════════════════════════════════════════════════════════════════


async def trigger_ingest_now() -> dict[str, Any]:
    """Manually trigger the ingest processor."""
    return await ingest_processor_once()


async def trigger_replay_now() -> dict[str, Any]:
    """Manually trigger the replay worker."""
    return await replay_worker_once()


async def trigger_pull(provider: str) -> dict[str, Any]:
    """Manually trigger a pull worker."""
    if provider == "hotelrunner":
        return await hotelrunner_pull_once()
    elif provider == "exely":
        return await exely_pull_once()
    else:
        return {"error": f"Unknown provider: {provider}"}
