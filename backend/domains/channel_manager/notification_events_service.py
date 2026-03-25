"""
Notification Events Service — High-Signal Event System
=======================================================

Emits operational events for critical state transitions.
Each event has a severity level and cooldown to prevent spam.

Event Severity Model:
  INFO     — positive state change (tenant_became_ready, mapping_complete)
  WARNING  — degradation detected (mapping_broken, drift spike)
  CRITICAL — operational risk (verify_failure_spike, auto_heal_failure)
  BLOCKER  — immediate action needed (tenant_fell_out_of_ready)

Cooldown / Deduplication:
  - Each event_type has a cooldown_seconds
  - State-change events fire only on actual transitions (not repeated states)
  - Spike events use threshold + cooldown combo
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger("channel_manager.notifications")

COLL_NOTIFICATION_EVENTS = "notification_events"
COLL_NOTIFICATION_STATE = "notification_state"
_NO_ID = {"_id": 0}


class EventSeverity:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    BLOCKER = "blocker"


class EventType:
    TENANT_BECAME_READY = "tenant_became_ready"
    TENANT_FELL_OUT_OF_READY = "tenant_fell_out_of_ready"
    MAPPING_COMPLETENESS_100 = "mapping_completeness_100"
    MAPPING_BROKEN_DETECTED = "mapping_broken_detected"
    HARD_FAIL_CLEARED = "hard_fail_cleared"
    HARD_FAIL_SPIKE = "hard_fail_spike"
    AUTO_HEAL_SUCCESS = "auto_heal_success"
    AUTO_HEAL_FAILURE_SPIKE = "auto_heal_failure_spike"
    FIRST_SUCCESSFUL_VERIFY = "first_successful_verify"
    VERIFY_FAILURE_SPIKE = "verify_failure_spike"


# Event configuration: severity + cooldown
EVENT_CONFIG = {
    EventType.TENANT_BECAME_READY: {
        "severity": EventSeverity.INFO,
        "cooldown_seconds": 0,  # state-change only, no cooldown needed
        "description": "Tenant production-ready durumuna gecti",
        "is_state_change": True,
    },
    EventType.TENANT_FELL_OUT_OF_READY: {
        "severity": EventSeverity.BLOCKER,
        "cooldown_seconds": 0,  # state-change only
        "description": "Tenant production-ready durumundan cikti",
        "is_state_change": True,
    },
    EventType.MAPPING_COMPLETENESS_100: {
        "severity": EventSeverity.INFO,
        "cooldown_seconds": 0,  # state-change only
        "description": "Mapping tamamlanma orani %100'e ulasti",
        "is_state_change": True,
    },
    EventType.MAPPING_BROKEN_DETECTED: {
        "severity": EventSeverity.WARNING,
        "cooldown_seconds": 600,  # 10 min cooldown
        "description": "Kirik mapping tespit edildi",
        "is_state_change": False,
    },
    EventType.HARD_FAIL_CLEARED: {
        "severity": EventSeverity.INFO,
        "cooldown_seconds": 0,  # state-change only
        "description": "Tum hard fail bloklari kaldirildi",
        "is_state_change": True,
    },
    EventType.HARD_FAIL_SPIKE: {
        "severity": EventSeverity.CRITICAL,
        "cooldown_seconds": 300,  # 5 min cooldown
        "description": "Hard fail sayisinda ani artis",
        "is_state_change": False,
    },
    EventType.AUTO_HEAL_SUCCESS: {
        "severity": EventSeverity.INFO,
        "cooldown_seconds": 300,  # 5 min cooldown
        "description": "Auto-heal basariyla tamamlandi",
        "is_state_change": False,
    },
    EventType.AUTO_HEAL_FAILURE_SPIKE: {
        "severity": EventSeverity.CRITICAL,
        "cooldown_seconds": 300,  # 5 min cooldown
        "description": "Auto-heal basarisizlik artisi",
        "is_state_change": False,
    },
    EventType.FIRST_SUCCESSFUL_VERIFY: {
        "severity": EventSeverity.INFO,
        "cooldown_seconds": 0,  # one-time event
        "description": "Ilk basarili provider dogrulama",
        "is_state_change": True,
    },
    EventType.VERIFY_FAILURE_SPIKE: {
        "severity": EventSeverity.CRITICAL,
        "cooldown_seconds": 300,  # 5 min cooldown
        "description": "Provider dogrulama basarisizlik artisi",
        "is_state_change": False,
    },
}


async def emit_event(
    tenant_id: str,
    event_type: str,
    details: dict[str, Any] | None = None,
    provider: str = "",
    property_id: str = "",
) -> dict[str, Any] | None:
    """
    Emit a notification event with deduplication and cooldown.
    Returns the event dict if emitted, None if suppressed.
    """
    config = EVENT_CONFIG.get(event_type)
    if not config:
        logger.warning(f"Unknown event type: {event_type}")
        return None

    now = datetime.now(UTC)
    now_iso = now.isoformat()

    # Cooldown check (non state-change events)
    cooldown = config["cooldown_seconds"]
    if cooldown > 0:
        cutoff = (now - timedelta(seconds=cooldown)).isoformat()
        recent = await db[COLL_NOTIFICATION_EVENTS].find_one({
            "tenant_id": tenant_id,
            "event_type": event_type,
            "provider": provider,
            "timestamp": {"$gte": cutoff},
        })
        if recent:
            return None  # suppressed by cooldown

    # State-change deduplication
    if config.get("is_state_change"):
        last_state = await _get_last_state(tenant_id, event_type, provider)
        if last_state == event_type:
            return None  # already in this state, suppress

        await _set_state(tenant_id, event_type, provider)

    event = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "event_type": event_type,
        "severity": config["severity"],
        "description": config["description"],
        "details": details or {},
        "provider": provider,
        "property_id": property_id,
        "timestamp": now_iso,
    }

    await db[COLL_NOTIFICATION_EVENTS].insert_one(event)

    # Dispatch to Slack if severity is CRITICAL or BLOCKER
    if config["severity"] in (EventSeverity.CRITICAL, EventSeverity.BLOCKER):
        await _dispatch_to_slack(tenant_id, event)

    logger.info(
        f"Event emitted: [{config['severity'].upper()}] {event_type} "
        f"tenant={tenant_id} provider={provider}"
    )
    return {k: v for k, v in event.items() if k != "_id"}


async def _get_last_state(tenant_id: str, event_type: str, provider: str) -> str | None:
    """Get the last known state for state-change deduplication."""
    doc = await db[COLL_NOTIFICATION_STATE].find_one(
        {"tenant_id": tenant_id, "state_key": event_type, "provider": provider},
        _NO_ID,
    )
    return doc.get("last_event_type") if doc else None


async def _set_state(tenant_id: str, event_type: str, provider: str) -> None:
    """Set the current state for state-change tracking."""
    await db[COLL_NOTIFICATION_STATE].update_one(
        {"tenant_id": tenant_id, "state_key": event_type, "provider": provider},
        {"$set": {
            "last_event_type": event_type,
            "updated_at": datetime.now(UTC).isoformat(),
        }},
        upsert=True,
    )


async def _dispatch_to_slack(tenant_id: str, event: dict[str, Any]) -> None:
    """Forward high-severity events to Slack via existing dispatch."""
    try:
        from domains.channel_manager.monitoring.alert_dispatch import dispatch_alert
        await dispatch_alert({
            "title": event["description"],
            "severity": "critical" if event["severity"] == EventSeverity.BLOCKER else event["severity"],
            "alert_type": event["event_type"],
            "provider": event.get("provider", "system"),
            "details": str(event.get("details", "")),
        }, tenant_id)
    except Exception as e:
        logger.warning(f"Slack dispatch failed for event {event['event_type']}: {e}")


async def evaluate_tenant_readiness(tenant_id: str, property_id: str = "default") -> dict[str, Any]:
    """
    Evaluate tenant readiness and emit appropriate events.
    This is the main evaluation function called periodically or on demand.
    """
    from domains.channel_manager import unified_repository as repo
    from domains.channel_manager.ari.hard_fail_gate import get_hard_fail_stats
    from domains.channel_manager.ari.push_loop_worker import get_push_worker
    from domains.channel_manager.auto_heal_service import get_auto_heal_stats
    from domains.channel_manager.mapping_validator import compute_mapping_health

    events_emitted = []

    # 1. Mapping completeness check
    for provider in ["exely", "hotelrunner"]:
        room_maps = await repo.get_room_mappings(tenant_id, property_id, provider)
        rate_maps = await repo.get_rate_plan_mappings(tenant_id, property_id, provider)
        health = await compute_mapping_health(tenant_id, property_id, provider, room_maps, rate_maps)

        if health.get("is_production_ready"):
            evt = await emit_event(
                tenant_id, EventType.MAPPING_COMPLETENESS_100,
                details={"provider": provider, "completeness": health.get("completeness_pct", 100)},
                provider=provider, property_id=property_id,
            )
            if evt:
                events_emitted.append(evt)
        elif health.get("broken_count", 0) > 0:
            evt = await emit_event(
                tenant_id, EventType.MAPPING_BROKEN_DETECTED,
                details={"provider": provider, "broken_count": health.get("broken_count", 0)},
                provider=provider, property_id=property_id,
            )
            if evt:
                events_emitted.append(evt)

    # 2. Hard fail stats
    hf_stats = await get_hard_fail_stats(tenant_id)
    if hf_stats["hard_fail_change_sets"] == 0 and hf_stats["hard_fails_last_24h"] == 0:
        evt = await emit_event(
            tenant_id, EventType.HARD_FAIL_CLEARED,
            details=hf_stats, property_id=property_id,
        )
        if evt:
            events_emitted.append(evt)
    elif hf_stats["hard_fails_last_24h"] > 5:
        evt = await emit_event(
            tenant_id, EventType.HARD_FAIL_SPIKE,
            details={"count_24h": hf_stats["hard_fails_last_24h"]},
            property_id=property_id,
        )
        if evt:
            events_emitted.append(evt)

    # 3. Auto-heal stats
    ah_stats = await get_auto_heal_stats(tenant_id)
    if ah_stats["total_failed"] > 3:
        evt = await emit_event(
            tenant_id, EventType.AUTO_HEAL_FAILURE_SPIKE,
            details={"total_failed": ah_stats["total_failed"]},
            property_id=property_id,
        )
        if evt:
            events_emitted.append(evt)

    # 4. Push loop verify stats
    worker = get_push_worker()
    metrics = worker.metrics.to_dict()
    if metrics["verify_fail_count"] > 5 and metrics["verify_success_ratio"] < 0.8:
        evt = await emit_event(
            tenant_id, EventType.VERIFY_FAILURE_SPIKE,
            details={
                "verify_fail_count": metrics["verify_fail_count"],
                "verify_success_ratio": metrics["verify_success_ratio"],
            },
            property_id=property_id,
        )
        if evt:
            events_emitted.append(evt)
    elif metrics["verify_success_count"] > 0 and metrics["verify_fail_count"] == 0:
        evt = await emit_event(
            tenant_id, EventType.FIRST_SUCCESSFUL_VERIFY,
            details={"verify_success_count": metrics["verify_success_count"]},
            property_id=property_id,
        )
        if evt:
            events_emitted.append(evt)

    # 5. Overall readiness (READY / NOT READY transition)
    is_ready = (
        hf_stats["hard_fail_change_sets"] == 0
        and hf_stats["open_hard_fail_incidents"] == 0
    )

    if is_ready:
        evt = await emit_event(
            tenant_id, EventType.TENANT_BECAME_READY,
            details={"hard_fail_stats": hf_stats},
            property_id=property_id,
        )
        if evt:
            events_emitted.append(evt)
    else:
        evt = await emit_event(
            tenant_id, EventType.TENANT_FELL_OUT_OF_READY,
            details={
                "hard_fail_change_sets": hf_stats["hard_fail_change_sets"],
                "open_incidents": hf_stats["open_hard_fail_incidents"],
            },
            property_id=property_id,
        )
        if evt:
            events_emitted.append(evt)

    return {
        "tenant_id": tenant_id,
        "is_ready": is_ready,
        "events_emitted": len(events_emitted),
        "events": events_emitted,
    }


async def get_event_history(
    tenant_id: str,
    severity: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict[str, Any]]:
    """Get notification event history with filters."""
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if severity:
        query["severity"] = severity
    if event_type:
        query["event_type"] = event_type

    return await db[COLL_NOTIFICATION_EVENTS].find(
        query, _NO_ID,
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)


async def get_event_summary(tenant_id: str) -> dict[str, Any]:
    """Summary of notification events for dashboard."""
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {
            "_id": {"severity": "$severity", "event_type": "$event_type"},
            "count": {"$sum": 1},
            "last_at": {"$max": "$timestamp"},
        }},
    ]
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total = 0

    async for doc in db[COLL_NOTIFICATION_EVENTS].aggregate(pipeline):
        severity = doc["_id"]["severity"]
        event_type = doc["_id"]["event_type"]
        count = doc["count"]
        total += count
        by_severity[severity] = by_severity.get(severity, 0) + count
        by_type[event_type] = by_type.get(event_type, 0) + count

    # Last 24h count
    since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    recent = await db[COLL_NOTIFICATION_EVENTS].count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": since},
    })

    return {
        "total_events": total,
        "events_last_24h": recent,
        "by_severity": by_severity,
        "by_type": by_type,
    }


def get_event_config() -> dict[str, Any]:
    """Return the event configuration (types, severities, cooldowns)."""
    return {
        event_type: {
            "severity": config["severity"],
            "cooldown_seconds": config["cooldown_seconds"],
            "description": config["description"],
            "is_state_change": config.get("is_state_change", False),
        }
        for event_type, config in EVENT_CONFIG.items()
    }
