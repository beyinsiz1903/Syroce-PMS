"""
HotelRunner v2 — Shadow Observation Module
=============================================

7-day shadow observation plan for write-path readiness.
Collects daily snapshots, evaluates alert thresholds,
checks reservation ingest consistency, generates reports.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger("hrv2.observation")

COLL_OBSERVATION_SNAPSHOTS = "connector_observation_snapshots"
COLL_METRICS = "connector_metrics"
COLL_DLQ = "connector_dlq"
COLL_RECON_DRIFTS = "connector_reconciliation_drifts"
COLL_RAW_EVENTS = "raw_channel_events"
_NO_ID = {"_id": 0}

# ── Alert Thresholds ──────────────────────────────────────────────────
ALERT_THRESHOLDS = {
    "drift_count_24h": {"warn": 5, "critical": 15, "description": "Son 24 saatte tespit edilen drift sayisi"},
    "retry_count_24h": {"warn": 10, "critical": 30, "description": "Son 24 saatte toplam retry sayisi"},
    "dlq_count": {"warn": 1, "critical": 5, "description": "Dead Letter Queue'da bekleyen kayit sayisi"},
    "error_rate_pct": {"warn": 5.0, "critical": 15.0, "description": "Hata orani yuzde (basarisiz/toplam)"},
    "avg_latency_ms": {"warn": 3000, "critical": 8000, "description": "Ortalama islem suresi (ms)"},
    "auth_failure_count": {"warn": 1, "critical": 3, "description": "Son 24 saatte auth hatasi sayisi"},
    "duplicate_ingest_count": {"warn": 3, "critical": 10, "description": "Tekrar edilen ingest sayisi"},
    "stale_reservation_count": {"warn": 5, "critical": 15, "description": "Guncellenmemis (stale) rezervasyon sayisi"},
}


def evaluate_threshold(metric_name: str, value: float) -> dict[str, Any]:
    """Evaluate a single metric against its threshold."""
    t = ALERT_THRESHOLDS.get(metric_name)
    if not t:
        return {"status": "unknown", "value": value}

    if value >= t["critical"]:
        status = "critical"
    elif value >= t["warn"]:
        status = "warn"
    else:
        status = "ok"

    return {
        "status": status,
        "value": value,
        "warn_threshold": t["warn"],
        "critical_threshold": t["critical"],
        "description": t["description"],
    }


# ── Daily Snapshot Collection ──────────────────────────────────────────


async def collect_daily_snapshot(tenant_id: str) -> dict[str, Any]:
    """
    Collect a comprehensive daily snapshot of all shadow observation metrics.
    Stores the snapshot in DB and returns it.
    """
    now = datetime.now(UTC)
    since_24h = (now - timedelta(hours=24)).isoformat()
    now_iso = now.isoformat()

    # 1. Metrics summary from connector_metrics
    metrics_pipeline = [
        {"$match": {"tenant_id": tenant_id, "provider": "hotelrunner_v2", "recorded_at": {"$gte": since_24h}}},
        {
            "$group": {
                "_id": None,
                "total_ops": {"$sum": 1},
                "success_count": {"$sum": {"$cond": ["$success", 1, 0]}},
                "fail_count": {"$sum": {"$cond": ["$success", 0, 1]}},
                "avg_latency": {"$avg": "$duration_ms"},
                "max_latency": {"$max": "$duration_ms"},
            }
        },
    ]
    agg = await db[COLL_METRICS].aggregate(metrics_pipeline).to_list(1)
    m = agg[0] if agg else {"total_ops": 0, "success_count": 0, "fail_count": 0, "avg_latency": 0, "max_latency": 0}

    total_ops = m["total_ops"]
    error_rate = round((m["fail_count"] / total_ops * 100), 2) if total_ops > 0 else 0.0
    avg_latency = round(m["avg_latency"] or 0, 1)

    # 2. Auth failure count
    auth_failures = await db[COLL_METRICS].count_documents(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner_v2",
            "recorded_at": {"$gte": since_24h},
            "error_category": "auth",
        }
    )

    # 3. Drift count (24h)
    drift_count = await db[COLL_RECON_DRIFTS].count_documents(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner_v2",
            "created_at": {"$gte": since_24h},
        }
    )

    # 4. DLQ count
    dlq_count = await db[COLL_DLQ].count_documents(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner",
        }
    )

    # 5. Retry count (failed ops = retries needed)
    retry_count = m["fail_count"]

    # 6. Ingest consistency
    consistency = await check_ingest_consistency(tenant_id, hours=24)

    # 7. Error taxonomy
    err_pipeline = [
        {"$match": {"tenant_id": tenant_id, "provider": "hotelrunner_v2", "recorded_at": {"$gte": since_24h}, "success": False}},
        {"$group": {"_id": "$error_category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    err_results = await db[COLL_METRICS].aggregate(err_pipeline).to_list(20)
    error_taxonomy = {r["_id"]: r["count"] for r in err_results if r["_id"]}

    # Build snapshot
    snapshot = {
        "tenant_id": tenant_id,
        "snapshot_date": now_iso,
        "day_label": now.strftime("%Y-%m-%d"),
        "metrics": {
            "total_operations": total_ops,
            "success_count": m["success_count"],
            "fail_count": m["fail_count"],
            "error_rate_pct": error_rate,
            "avg_latency_ms": avg_latency,
            "max_latency_ms": m["max_latency"] or 0,
            "auth_failure_count": auth_failures,
            "drift_count_24h": drift_count,
            "dlq_count": dlq_count,
            "retry_count_24h": retry_count,
            "duplicate_ingest_count": consistency.get("duplicate_count", 0),
            "stale_reservation_count": consistency.get("stale_count", 0),
        },
        "error_taxonomy": error_taxonomy,
        "ingest_consistency": consistency,
        "alerts": {},
    }

    # Evaluate thresholds
    alerts = {}
    for metric_key in ALERT_THRESHOLDS:
        value = snapshot["metrics"].get(metric_key, 0)
        alerts[metric_key] = evaluate_threshold(metric_key, value)
    snapshot["alerts"] = alerts

    # Count alert severities
    snapshot["alert_summary"] = {
        "critical_count": sum(1 for a in alerts.values() if a["status"] == "critical"),
        "warn_count": sum(1 for a in alerts.values() if a["status"] == "warn"),
        "ok_count": sum(1 for a in alerts.values() if a["status"] == "ok"),
    }

    # Store in DB
    await db[COLL_OBSERVATION_SNAPSHOTS].update_one(
        {"tenant_id": tenant_id, "day_label": snapshot["day_label"]},
        {"$set": snapshot},
        upsert=True,
    )

    return snapshot


async def check_ingest_consistency(tenant_id: str, hours: int = 24) -> dict[str, Any]:
    """
    Check reservation ingest consistency:
    - Duplicate detection: same external_reservation_id ingested multiple times
    - Stale detection: reservations not updated within threshold
    """
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    # Duplicate check: group by external_reservation_id, count > 1
    dup_pipeline = [
        {
            "$match": {
                "tenant_id": tenant_id,
                "provider": {"$in": ["hotelrunner", "hotelrunner_v2"]},
                "received_at": {"$gte": since},
            }
        },
        {
            "$group": {
                "_id": "$external_reservation_id",
                "count": {"$sum": 1},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
        {"$count": "duplicate_ids"},
    ]
    dup_result = await db[COLL_RAW_EVENTS].aggregate(dup_pipeline).to_list(1)
    duplicate_count = dup_result[0]["duplicate_ids"] if dup_result else 0

    # Stale check: reservations with last_seen_at older than 48 hours
    stale_threshold = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    stale_count = await db["reservation_lineage"].count_documents(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner",
            "last_seen_at": {"$lt": stale_threshold, "$gte": (datetime.now(UTC) - timedelta(days=7)).isoformat()},
        }
    )

    return {
        "duplicate_count": duplicate_count,
        "stale_count": stale_count,
        "check_period_hours": hours,
        "stale_threshold_hours": 48,
        "checked_at": datetime.now(UTC).isoformat(),
    }


# ── Observation History ──────────────────────────────────────────────


async def get_observation_history(tenant_id: str, days: int = 7) -> list[dict[str, Any]]:
    """Get observation snapshots for the last N days."""
    return (
        await db[COLL_OBSERVATION_SNAPSHOTS]
        .find(
            {"tenant_id": tenant_id},
            _NO_ID,
        )
        .sort("snapshot_date", -1)
        .to_list(days)
    )


async def get_alert_thresholds() -> dict[str, Any]:
    """Return current alert threshold definitions."""
    return ALERT_THRESHOLDS


async def generate_daily_report(tenant_id: str) -> dict[str, Any]:
    """
    Generate a formatted daily observation report.
    Combines latest snapshot + trend data from previous days.
    """
    snapshots = await get_observation_history(tenant_id, days=7)

    if not snapshots:
        return {
            "tenant_id": tenant_id,
            "status": "no_data",
            "message": "Henuz gunluk snapshot verisi yok. Ilk snapshot'i almak icin /observation/snapshot endpoint'ini kullanin.",
        }

    latest = snapshots[0]
    previous = snapshots[1:] if len(snapshots) > 1 else []

    # Calculate trends
    trends = {}
    if previous:
        prev_metrics = previous[0].get("metrics", {})
        curr_metrics = latest.get("metrics", {})
        for key in ["error_rate_pct", "drift_count_24h", "avg_latency_ms", "dlq_count", "retry_count_24h"]:
            curr_val = curr_metrics.get(key, 0)
            prev_val = prev_metrics.get(key, 0)
            if prev_val > 0:
                change_pct = round(((curr_val - prev_val) / prev_val) * 100, 1)
            elif curr_val > 0:
                change_pct = 100.0
            else:
                change_pct = 0.0
            direction = "up" if change_pct > 0 else "down" if change_pct < 0 else "stable"
            trends[key] = {"current": curr_val, "previous": prev_val, "change_pct": change_pct, "direction": direction}

    # Observation days completed
    observation_days = len(snapshots)

    return {
        "tenant_id": tenant_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "observation_day": observation_days,
        "observation_target": 7,
        "observation_complete": observation_days >= 7,
        "latest_snapshot": latest,
        "trends": trends,
        "history_summary": [
            {
                "day": s.get("day_label"),
                "total_ops": s.get("metrics", {}).get("total_operations", 0),
                "error_rate": s.get("metrics", {}).get("error_rate_pct", 0),
                "drift_count": s.get("metrics", {}).get("drift_count_24h", 0),
                "avg_latency": s.get("metrics", {}).get("avg_latency_ms", 0),
                "alerts_critical": s.get("alert_summary", {}).get("critical_count", 0),
                "alerts_warn": s.get("alert_summary", {}).get("warn_count", 0),
            }
            for s in snapshots
        ],
    }
