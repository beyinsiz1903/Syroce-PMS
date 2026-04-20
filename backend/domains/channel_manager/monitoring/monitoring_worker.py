"""
Operational Monitoring — Worker
=================================

Background worker running every 60 seconds:
  1. Collect system metrics
  2. Evaluate alert thresholds
  3. Create/resolve alert events
  4. Update dashboard metrics
  5. Store metrics snapshot for trend analysis
"""
import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

from .aggregator import collect_all_metrics
from .alert_engine import evaluate_alerts, process_alerts

logger = logging.getLogger("monitoring.worker")

COLL_METRICS_HISTORY = "monitoring_metrics_history"

import os as _os
_monitoring_state = {
    "running": False,
    "last_run": None,
    "interval_seconds": int(_os.getenv("SYROCE_MONITOR_INTERVAL", "300")),
    "runs_total": 0,
    "last_metrics": None,
    "last_alert_result": None,
    "errors": 0,
}

_task = None


def get_monitoring_worker_state() -> dict[str, Any]:
    return {**_monitoring_state}


def get_last_metrics() -> dict[str, Any]:
    return _monitoring_state.get("last_metrics") or {}


async def _store_metrics_snapshot(metrics: dict[str, Any]):
    """Store a compact metrics snapshot for trend analysis."""
    try:
        ingest = metrics.get("ingest_pipeline", {})
        ari = metrics.get("ari_push", {})
        recon = metrics.get("reconciliation", {})
        queue = metrics.get("queue_health", {})

        snapshot = {
            "ts": datetime.now(UTC).isoformat(),
            "health": metrics.get("system_health", "unknown"),
            "ingest_events_1h": ingest.get("events_last_1h", 0),
            "ingest_failed": ingest.get("failed_events", 0),
            "ingest_duplicates": ingest.get("duplicates_caught", 0),
            "ari_success_rate": ari.get("success_rate", 0),
            "ari_p95_latency": ari.get("p95_latency_ms", 0),
            "ari_retry_count": ari.get("retry_count", 0),
            "recon_open": recon.get("open_cases", 0),
            "recon_critical": recon.get("critical_cases", 0),
            "queue_depth": queue.get("queue_depth", 0),
            "retry_backlog": queue.get("retry_backlog", 0),
        }
        await db[COLL_METRICS_HISTORY].insert_one(snapshot)
    except Exception as e:
        logger.warning(f"Failed to store metrics snapshot: {e}")


async def monitoring_run_once() -> dict[str, Any]:
    """Execute a single monitoring cycle."""
    state = _monitoring_state

    try:
        metrics = await collect_all_metrics()
        state["last_metrics"] = metrics

        alerts = await evaluate_alerts(metrics)
        alert_result = await process_alerts(alerts)
        state["last_alert_result"] = alert_result

        # Store snapshot for trends
        await _store_metrics_snapshot(metrics)

        state["runs_total"] += 1
        state["last_run"] = datetime.now(UTC).isoformat()

        logger.info(
            f"Monitoring cycle #{state['runs_total']}: "
            f"health={metrics.get('system_health')}, "
            f"alerts_created={alert_result.get('created', 0)}, "
            f"alerts_resolved={alert_result.get('resolved', 0)}"
        )

        return {
            "status": "completed",
            "system_health": metrics.get("system_health"),
            "alerts": alert_result,
            "collected_at": metrics.get("collected_at"),
        }
    except Exception as e:
        state["errors"] += 1
        logger.error(f"Monitoring worker error: {e}")
        return {"status": "error", "error": str(e)}


async def _monitoring_loop():
    """Continuous monitoring loop."""
    state = _monitoring_state
    while state["running"]:
        try:
            await monitoring_run_once()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Monitoring loop error: {e}")
        await asyncio.sleep(state["interval_seconds"])


async def start_monitoring_worker():
    """Start the background monitoring worker."""
    global _task
    state = _monitoring_state
    if state["running"]:
        return
    state["running"] = True
    _task = asyncio.create_task(_monitoring_loop())
    logger.info(f"Monitoring worker started ({_monitoring_state['interval_seconds']}s interval)")


async def stop_monitoring_worker():
    """Stop the background monitoring worker."""
    global _task
    _monitoring_state["running"] = False
    if _task:
        _task.cancel()
        _task = None
    logger.info("Monitoring worker stopped")
