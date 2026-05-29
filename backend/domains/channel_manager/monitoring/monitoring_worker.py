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
import os as _os
from datetime import UTC, datetime
from typing import Any

from core.database import db
from core.transient_db_guard import TransientFailureTracker

from .aggregator import collect_all_metrics
from .alert_engine import evaluate_alerts, process_alerts

logger = logging.getLogger("monitoring.worker")

_transient_tracker = TransientFailureTracker("monitoring-worker")

COLL_METRICS_HISTORY = "monitoring_metrics_history"

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
        # NOTE: aggregator returns keys `ingest_health`, `ari_health`,
        # `reconciliation_health`, `queue_health`. Older code here referenced
        # legacy keys (`ingest_pipeline`, `ari_push`, `reconciliation`); keep a
        # fallback so existing trend rows do not regress while the canonical
        # keys feed the new fields.
        ingest = metrics.get("ingest_health") or metrics.get("ingest_pipeline", {})
        ari = metrics.get("ari_health") or metrics.get("ari_push", {})
        recon = metrics.get("reconciliation_health") or metrics.get("reconciliation", {})
        queue = metrics.get("queue_health", {})

        snapshot = {
            "ts": datetime.now(UTC).isoformat(),
            "health": metrics.get("system_health", "unknown"),
            "ingest_events_1h": ingest.get("recent_events_1h", ingest.get("events_last_1h", 0)),
            "ingest_failed": ingest.get("failed", ingest.get("failed_events", 0)),
            "ingest_duplicates": ingest.get("duplicates", ingest.get("duplicates_caught", 0)),
            "catchup_dedup_1h": ingest.get("catchup_dedup_skips_1h", 0),
            "catchup_dedup_24h": ingest.get("catchup_dedup_skips_24h", 0),
            "ari_success_rate": ari.get("success_rate", 0),
            "ari_p95_latency": ari.get("latency_p95", ari.get("p95_latency_ms", 0)),
            "ari_retry_count": ari.get("retry_count", 0),
            "recon_open": recon.get("open_cases", 0),
            "recon_critical": recon.get("critical_count", recon.get("critical_cases", 0)),
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
        _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)

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
        # Transient Atlas hiccups (no-primary / SSL handshake timeout) are
        # demoted to WARNING until sustained; real bugs stay ERROR (Sentry).
        _transient_tracker.log_exception(
            logger,
            e,
            TransientFailureTracker.OUTER_LOOP_KEY,
            context="monitoring cycle",
            non_transient_msg="%s monitoring worker error: %s",
        )
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
