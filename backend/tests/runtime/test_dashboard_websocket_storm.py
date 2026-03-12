"""
Runtime Stress Tests — Dashboard WebSocket Event Storm
Simulates high-frequency system health events via MongoDB
and validates event persistence under burst conditions.
"""
import asyncio
import pytest
import uuid
from datetime import datetime, timezone


async def test_websocket_event_storm(db):
    """Insert 200 system health events concurrently — verify all persisted."""
    tid = f"stress-ws-{uuid.uuid4().hex[:8]}"

    async def emit_event(idx):
        event = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "event_type": ["queue_depth_high", "drift_detected", "worker_stalled", "rate_limit_burst"][idx % 4],
            "severity": ["info", "warning", "critical"][idx % 3],
            "source": "stress_test",
            "data": {"value": idx, "metric": f"m-{idx}"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await db.system_health_events.insert_one(event)
        return event

    tasks = [emit_event(i) for i in range(200)]
    results = await asyncio.gather(*tasks)
    assert len(results) == 200

    count = await db.system_health_events.count_documents({"tenant_id": tid})
    assert count == 200

    critical = await db.system_health_events.count_documents({"tenant_id": tid, "severity": "critical"})
    assert critical > 0

    await db.system_health_events.delete_many({"tenant_id": tid})


async def test_concurrent_metric_updates(db):
    """Simulate concurrent metric updates from multiple subsystems."""
    tid = f"stress-metrics-{uuid.uuid4().hex[:8]}"
    metric_id = str(uuid.uuid4())

    await db.runtime_metrics.insert_one({
        "id": metric_id,
        "tenant_id": tid,
        "metric_name": "queue_depth",
        "value": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    async def increment_metric(amount):
        await db.runtime_metrics.update_one(
            {"id": metric_id},
            {
                "$inc": {"value": amount},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
            },
        )

    tasks = [increment_metric(1) for _ in range(100)]
    await asyncio.gather(*tasks)

    metric = await db.runtime_metrics.find_one({"id": metric_id}, {"_id": 0})
    assert metric["value"] == 100

    await db.runtime_metrics.delete_many({"tenant_id": tid})


async def test_alert_aggregation_under_load(db):
    """Create alerts from multiple sources simultaneously."""
    tid = f"stress-alert-{uuid.uuid4().hex[:8]}"

    async def create_alert(idx):
        alert = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "type": ["cm_drift", "queue_saturation", "security_violation", "worker_stuck"][idx % 4],
            "severity": "critical" if idx % 10 == 0 else ("warning" if idx % 3 == 0 else "info"),
            "message": f"Alert from source {idx}",
            "resolved": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.runtime_alerts.insert_one(alert)
        return alert

    tasks = [create_alert(i) for i in range(100)]
    results = await asyncio.gather(*tasks)

    total = await db.runtime_alerts.count_documents({"tenant_id": tid})
    assert total == 100

    critical = await db.runtime_alerts.count_documents({"tenant_id": tid, "severity": "critical"})
    assert critical >= 10

    unresolved = await db.runtime_alerts.count_documents({"tenant_id": tid, "resolved": False})
    assert unresolved == 100

    await db.runtime_alerts.delete_many({"tenant_id": tid})
