"""
HotelRunner v2 — Shadow Automation Engine
============================================

Celery Beat ile calisan periyodik gorevler:

6 saatte bir:
  1. Provider health snapshot
  2. Sync metrics snapshot
  3. Drift snapshot
  4. DLQ / retry snapshot
  5. Readiness score recalculation
  6. Otomatik dry-run chain testi
  7. Sonuclarin history olarak saklanmasi
  8. Alert uretimi (threshold ihlalleri)

Gunde 1 kez:
  - Ozet rapor uretimi
  - Son 24 saatin trendi
  - Readiness score degisimi

Retention:
  - Ham snapshotlar: 30 gun
  - Gunluk ozetler: 90 gun
"""
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger("hrv2.shadow_automation")

COLL_AUTO_SNAPSHOTS = "connector_auto_snapshots"
COLL_AUTO_ALERTS = "connector_auto_alerts"
COLL_DAILY_SUMMARIES = "connector_daily_summaries"
COLL_OBSERVATION_SNAPSHOTS = "connector_observation_snapshots"
_NO_ID = {"_id": 0}

DEFAULT_TENANT = "default"

# ── Alert Thresholds ──────────────────────────────────────────────────

ALERT_RULES = {
    "readiness_low": {
        "label": "Readiness Score dusuk",
        "check": lambda snap: snap.get("readiness", {}).get("overall_score", 100) < 70,
        "severity": "critical",
        "message_fn": lambda snap: f"Readiness Score {snap.get('readiness', {}).get('overall_score', 0)} — esik: 70",
    },
    "readiness_warn": {
        "label": "Readiness Score uyari",
        "check": lambda snap: 70 <= snap.get("readiness", {}).get("overall_score", 100) < 85,
        "severity": "warn",
        "message_fn": lambda snap: f"Readiness Score {snap.get('readiness', {}).get('overall_score', 0)} — esik: 85",
    },
    "drift_high": {
        "label": "Drift artisi",
        "check": lambda snap: snap.get("observation", {}).get("metrics", {}).get("drift_count_24h", 0) >= 5,
        "severity": "critical",
        "message_fn": lambda snap: f"Drift count: {snap.get('observation', {}).get('metrics', {}).get('drift_count_24h', 0)}",
    },
    "dlq_nonempty": {
        "label": "DLQ bos degil",
        "check": lambda snap: snap.get("observation", {}).get("metrics", {}).get("dlq_count", 0) > 0,
        "severity": "critical",
        "message_fn": lambda snap: f"DLQ count: {snap.get('observation', {}).get('metrics', {}).get('dlq_count', 0)}",
    },
    "auth_failure": {
        "label": "Auth failure tespit edildi",
        "check": lambda snap: snap.get("observation", {}).get("metrics", {}).get("auth_failure_count", 0) > 0,
        "severity": "critical",
        "message_fn": lambda snap: f"Auth failure: {snap.get('observation', {}).get('metrics', {}).get('auth_failure_count', 0)}",
    },
    "dry_run_chain_fail": {
        "label": "Dry-run chain testi basarisiz",
        "check": lambda snap: snap.get("dry_run_chain") is not None and not snap.get("dry_run_chain", {}).get("success", True),
        "severity": "critical",
        "message_fn": lambda snap: f"Chain test basarisiz — correlation: {snap.get('dry_run_chain', {}).get('correlation_id', 'N/A')}",
    },
}


# ── 6-Hourly Snapshot ─────────────────────────────────────────────────

async def run_periodic_snapshot(tenant_id: str) -> dict[str, Any]:
    """
    6 saatte bir calisan tam snapshot:
    1. observation snapshot
    2. readiness score
    3. dry-run chain test
    4. alert uretimi
    """
    now = datetime.now(UTC)
    now_iso = now.isoformat()

    logger.info("[Shadow Auto] 6-saatlik snapshot baslatiliyor — tenant=%s", tenant_id)

    # 1. Observation snapshot (metrics, drift, DLQ, retry, consistency)
    from .observation import collect_daily_snapshot
    observation = await collect_daily_snapshot(tenant_id)

    # 2. Readiness score
    from .readiness import calculate_readiness_score
    readiness = await calculate_readiness_score(tenant_id)

    # 3. Automatic dry-run chain test
    dry_run_chain_result = None
    try:
        from .dry_run import dry_run_chain
        dry_run_chain_result = await dry_run_chain(tenant_id, "default")
        logger.info("[Shadow Auto] Dry-run chain tamamlandi — success=%s", dry_run_chain_result.get("success"))
    except Exception as e:
        logger.error("[Shadow Auto] Dry-run chain hatasi: %s", e)
        dry_run_chain_result = {"success": False, "error": str(e)}

    # 4. Write criteria check
    from .dry_run import check_write_enable_criteria
    write_criteria = await check_write_enable_criteria(tenant_id)

    # Build combined snapshot
    snapshot = {
        "tenant_id": tenant_id,
        "snapshot_type": "periodic_6h",
        "created_at": now_iso,
        "timestamp_label": now.strftime("%Y-%m-%d %H:%M"),
        "observation": {
            "metrics": observation.get("metrics", {}),
            "alert_summary": observation.get("alert_summary", {}),
            "error_taxonomy": observation.get("error_taxonomy", {}),
            "ingest_consistency": observation.get("ingest_consistency", {}),
        },
        "readiness": {
            "overall_score": readiness.get("overall_score", 0),
            "verdict": readiness.get("verdict", "no_data"),
            "components": readiness.get("components", {}),
            "raw_metrics": readiness.get("raw_metrics", {}),
        },
        "dry_run_chain": {
            "success": dry_run_chain_result.get("success", False) if dry_run_chain_result else None,
            "step_count": dry_run_chain_result.get("step_count", 0) if dry_run_chain_result else 0,
            "success_count": dry_run_chain_result.get("success_count", 0) if dry_run_chain_result else 0,
            "failure_count": dry_run_chain_result.get("failure_count", 0) if dry_run_chain_result else 0,
            "duration_ms": dry_run_chain_result.get("duration_ms", 0) if dry_run_chain_result else 0,
            "correlation_id": dry_run_chain_result.get("correlation_id", "") if dry_run_chain_result else "",
        } if dry_run_chain_result else None,
        "write_criteria": {
            "all_met": write_criteria.get("all_criteria_met", False),
            "met_count": write_criteria.get("met_count", 0),
            "total_criteria": write_criteria.get("total_criteria", 0),
        },
    }

    # Store snapshot
    await db[COLL_AUTO_SNAPSHOTS].insert_one({**snapshot})

    # 5. Alert generation
    alerts = await _evaluate_alerts(tenant_id, snapshot)
    snapshot["alerts_generated"] = len(alerts)

    logger.info(
        "[Shadow Auto] Snapshot tamamlandi — readiness=%s, alerts=%d, chain_success=%s",
        readiness.get("overall_score", 0),
        len(alerts),
        dry_run_chain_result.get("success") if dry_run_chain_result else "N/A",
    )

    snapshot.pop("_id", None)
    return snapshot


async def _evaluate_alerts(tenant_id: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate all alert rules against the snapshot."""
    now_iso = datetime.now(UTC).isoformat()
    alerts = []

    for rule_id, rule in ALERT_RULES.items():
        try:
            if rule["check"](snapshot):
                alert = {
                    "tenant_id": tenant_id,
                    "rule_id": rule_id,
                    "label": rule["label"],
                    "severity": rule["severity"],
                    "message": rule["message_fn"](snapshot),
                    "snapshot_time": snapshot.get("created_at", now_iso),
                    "created_at": now_iso,
                    "acknowledged": False,
                }
                await db[COLL_AUTO_ALERTS].insert_one({**alert})
                alerts.append(alert)
                logger.warning("[Shadow Auto] ALERT: %s — %s", rule_id, alert["message"])
        except Exception as e:
            logger.error("[Shadow Auto] Alert check failed for %s: %s", rule_id, e)

    return alerts


# ── Daily Summary ─────────────────────────────────────────────────────

async def generate_daily_summary(tenant_id: str) -> dict[str, Any]:
    """
    Gunde 1 kez calisan ozet rapor:
    - Son 24 saatin trendi
    - Readiness score degisimi
    - Alert ozeti
    - Dry-run chain sonuclari
    """
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    since_24h = (now - timedelta(hours=24)).isoformat()
    since_48h = (now - timedelta(hours=48)).isoformat()

    logger.info("[Shadow Auto] Gunluk ozet uretiliyor — tenant=%s", tenant_id)

    # Get today's snapshots (last 24h)
    today_snapshots = await db[COLL_AUTO_SNAPSHOTS].find(
        {"tenant_id": tenant_id, "created_at": {"$gte": since_24h}},
        _NO_ID,
    ).sort("created_at", 1).to_list(10)

    # Get yesterday's snapshots (24-48h ago)
    yesterday_snapshots = await db[COLL_AUTO_SNAPSHOTS].find(
        {"tenant_id": tenant_id, "created_at": {"$gte": since_48h, "$lt": since_24h}},
        _NO_ID,
    ).sort("created_at", 1).to_list(10)

    # Readiness trend
    readiness_trend = [
        {
            "time": s.get("timestamp_label", ""),
            "score": s.get("readiness", {}).get("overall_score", 0),
            "verdict": s.get("readiness", {}).get("verdict", "no_data"),
        }
        for s in today_snapshots
    ]

    # Drift trend
    drift_trend = [
        {
            "time": s.get("timestamp_label", ""),
            "count": s.get("observation", {}).get("metrics", {}).get("drift_count_24h", 0),
        }
        for s in today_snapshots
    ]

    # Latency trend
    latency_trend = [
        {
            "time": s.get("timestamp_label", ""),
            "avg_ms": s.get("observation", {}).get("metrics", {}).get("avg_latency_ms", 0),
        }
        for s in today_snapshots
    ]

    # Failure trend
    failure_trend = [
        {
            "time": s.get("timestamp_label", ""),
            "error_rate": s.get("observation", {}).get("metrics", {}).get("error_rate_pct", 0),
            "fail_count": s.get("observation", {}).get("metrics", {}).get("fail_count", 0),
        }
        for s in today_snapshots
    ]

    # Score change (vs yesterday)
    today_avg_score = 0
    yesterday_avg_score = 0
    if today_snapshots:
        today_avg_score = round(
            sum(s.get("readiness", {}).get("overall_score", 0) for s in today_snapshots) / len(today_snapshots), 1
        )
    if yesterday_snapshots:
        yesterday_avg_score = round(
            sum(s.get("readiness", {}).get("overall_score", 0) for s in yesterday_snapshots) / len(yesterday_snapshots), 1
        )

    score_change = round(today_avg_score - yesterday_avg_score, 1)
    score_direction = "up" if score_change > 0 else "down" if score_change < 0 else "stable"

    # Alert summary (last 24h)
    alerts_24h = await db[COLL_AUTO_ALERTS].find(
        {"tenant_id": tenant_id, "created_at": {"$gte": since_24h}},
        _NO_ID,
    ).to_list(100)
    alert_summary = {
        "total": len(alerts_24h),
        "critical": sum(1 for a in alerts_24h if a.get("severity") == "critical"),
        "warn": sum(1 for a in alerts_24h if a.get("severity") == "warn"),
    }

    # Chain test summary
    chain_results = [
        s.get("dry_run_chain", {})
        for s in today_snapshots
        if s.get("dry_run_chain")
    ]
    chain_summary = {
        "total_runs": len(chain_results),
        "success_count": sum(1 for c in chain_results if c.get("success")),
        "fail_count": sum(1 for c in chain_results if not c.get("success")),
    }

    # Latest write criteria
    latest_criteria = None
    if today_snapshots:
        latest_criteria = today_snapshots[-1].get("write_criteria")

    summary = {
        "tenant_id": tenant_id,
        "summary_type": "daily",
        "summary_date": now.strftime("%Y-%m-%d"),
        "created_at": now_iso,
        "period": {"start": since_24h, "end": now_iso},
        "snapshot_count": len(today_snapshots),
        "readiness": {
            "current_score": today_avg_score,
            "previous_score": yesterday_avg_score,
            "change": score_change,
            "direction": score_direction,
            "trend": readiness_trend,
        },
        "drift": {
            "trend": drift_trend,
            "latest": drift_trend[-1]["count"] if drift_trend else 0,
        },
        "latency": {
            "trend": latency_trend,
            "latest_avg_ms": latency_trend[-1]["avg_ms"] if latency_trend else 0,
        },
        "failures": {
            "trend": failure_trend,
            "latest_error_rate": failure_trend[-1]["error_rate"] if failure_trend else 0,
        },
        "alerts": alert_summary,
        "chain_tests": chain_summary,
        "write_criteria": latest_criteria,
    }

    # Store summary
    await db[COLL_DAILY_SUMMARIES].update_one(
        {"tenant_id": tenant_id, "summary_date": summary["summary_date"]},
        {"$set": summary},
        upsert=True,
    )

    logger.info(
        "[Shadow Auto] Gunluk ozet tamamlandi — score=%s (change=%s), alerts=%d",
        today_avg_score, score_change, alert_summary["total"],
    )

    return summary


# ── Retention Cleanup ─────────────────────────────────────────────────

async def cleanup_old_data() -> dict[str, int]:
    """
    Retention politikasi:
    - Ham snapshotlar: 30 gun
    - Gunluk ozetler: 90 gun
    - Eski alertler: 60 gun
    """
    now = datetime.now(UTC)

    # Snapshots: 30 gun
    snapshot_cutoff = (now - timedelta(days=30)).isoformat()
    snap_result = await db[COLL_AUTO_SNAPSHOTS].delete_many(
        {"created_at": {"$lt": snapshot_cutoff}}
    )

    # Daily summaries: 90 gun
    summary_cutoff = (now - timedelta(days=90)).isoformat()
    sum_result = await db[COLL_DAILY_SUMMARIES].delete_many(
        {"created_at": {"$lt": summary_cutoff}}
    )

    # Old observation snapshots: 30 gun
    obs_result = await db[COLL_OBSERVATION_SNAPSHOTS].delete_many(
        {"snapshot_date": {"$lt": snapshot_cutoff}}
    )

    # Alerts: 60 gun
    alert_cutoff = (now - timedelta(days=60)).isoformat()
    alert_result = await db[COLL_AUTO_ALERTS].delete_many(
        {"created_at": {"$lt": alert_cutoff}}
    )

    result = {
        "snapshots_deleted": snap_result.deleted_count,
        "summaries_deleted": sum_result.deleted_count,
        "observation_snapshots_deleted": obs_result.deleted_count,
        "alerts_deleted": alert_result.deleted_count,
        "cleaned_at": now.isoformat(),
    }
    logger.info("[Shadow Auto] Retention cleanup: %s", result)
    return result


# ── Automation Status ─────────────────────────────────────────────────

async def get_automation_status(tenant_id: str) -> dict[str, Any]:
    """Get current automation status and recent activity."""
    now = datetime.now(UTC)
    since_24h = (now - timedelta(hours=24)).isoformat()

    # Last snapshot
    last_snapshot = await db[COLL_AUTO_SNAPSHOTS].find_one(
        {"tenant_id": tenant_id},
        _NO_ID,
        sort=[("created_at", -1)],
    )

    # Snapshot count (24h)
    snapshot_count_24h = await db[COLL_AUTO_SNAPSHOTS].count_documents(
        {"tenant_id": tenant_id, "created_at": {"$gte": since_24h}},
    )

    # Last summary
    last_summary = await db[COLL_DAILY_SUMMARIES].find_one(
        {"tenant_id": tenant_id},
        _NO_ID,
        sort=[("created_at", -1)],
    )

    # Active alerts (unacknowledged)
    active_alerts = await db[COLL_AUTO_ALERTS].count_documents(
        {"tenant_id": tenant_id, "acknowledged": False},
    )

    # Total alerts (24h)
    alerts_24h = await db[COLL_AUTO_ALERTS].count_documents(
        {"tenant_id": tenant_id, "created_at": {"$gte": since_24h}},
    )

    return {
        "tenant_id": tenant_id,
        "automation_active": True,
        "schedule": {
            "snapshot_interval": "6 saat",
            "daily_summary": "Her gun 00:00 UTC",
            "retention_cleanup": "Haftada 1 (Pazar 05:00 UTC)",
        },
        "last_snapshot": {
            "created_at": last_snapshot.get("created_at") if last_snapshot else None,
            "readiness_score": last_snapshot.get("readiness", {}).get("overall_score") if last_snapshot else None,
            "chain_success": last_snapshot.get("dry_run_chain", {}).get("success") if last_snapshot and last_snapshot.get("dry_run_chain") else None,
        } if last_snapshot else None,
        "last_daily_summary": {
            "date": last_summary.get("summary_date") if last_summary else None,
            "readiness_score": last_summary.get("readiness", {}).get("current_score") if last_summary else None,
            "score_change": last_summary.get("readiness", {}).get("change") if last_summary else None,
        } if last_summary else None,
        "snapshots_24h": snapshot_count_24h,
        "active_alerts": active_alerts,
        "alerts_24h": alerts_24h,
        "checked_at": now.isoformat(),
    }


# ── Trend Data for Dashboard ──────────────────────────────────────────

async def get_trend_data(tenant_id: str, hours: int = 168) -> dict[str, Any]:
    """
    Dashboard trend paneli icin veri:
    - readiness_trend
    - drift_trend
    - latency_trend
    - failure_trend
    """
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    snapshots = await db[COLL_AUTO_SNAPSHOTS].find(
        {"tenant_id": tenant_id, "created_at": {"$gte": since}},
        _NO_ID,
    ).sort("created_at", 1).to_list(200)

    readiness_trend = []
    drift_trend = []
    latency_trend = []
    failure_trend = []

    for s in snapshots:
        time_label = s.get("timestamp_label", "")
        obs_metrics = s.get("observation", {}).get("metrics", {})

        readiness_trend.append({
            "time": time_label,
            "score": s.get("readiness", {}).get("overall_score", 0),
        })
        drift_trend.append({
            "time": time_label,
            "count": obs_metrics.get("drift_count_24h", 0),
        })
        latency_trend.append({
            "time": time_label,
            "avg_ms": obs_metrics.get("avg_latency_ms", 0),
        })
        failure_trend.append({
            "time": time_label,
            "error_rate": obs_metrics.get("error_rate_pct", 0),
            "fail_count": obs_metrics.get("fail_count", 0),
        })

    return {
        "tenant_id": tenant_id,
        "period_hours": hours,
        "data_points": len(snapshots),
        "readiness_trend": readiness_trend,
        "drift_trend": drift_trend,
        "latency_trend": latency_trend,
        "failure_trend": failure_trend,
    }


# ── Alert History ─────────────────────────────────────────────────────

async def get_alert_history(tenant_id: str, limit: int = 50, severity: str | None = None) -> list[dict[str, Any]]:
    """Get automation alert history."""
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if severity:
        query["severity"] = severity

    return await db[COLL_AUTO_ALERTS].find(
        query, _NO_ID,
    ).sort("created_at", -1).to_list(limit)


async def acknowledge_alert(tenant_id: str, rule_id: str, snapshot_time: str) -> dict[str, Any]:
    """Acknowledge a specific alert."""
    result = await db[COLL_AUTO_ALERTS].update_one(
        {"tenant_id": tenant_id, "rule_id": rule_id, "snapshot_time": snapshot_time},
        {"$set": {"acknowledged": True, "acknowledged_at": datetime.now(UTC).isoformat()}},
    )
    return {"modified": result.modified_count > 0}


# ── Daily Summary History ─────────────────────────────────────────────

async def get_daily_summaries(tenant_id: str, limit: int = 30) -> list[dict[str, Any]]:
    """Get daily summary history."""
    return await db[COLL_DAILY_SUMMARIES].find(
        {"tenant_id": tenant_id},
        _NO_ID,
    ).sort("created_at", -1).to_list(limit)
