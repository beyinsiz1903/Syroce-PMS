"""
Operational Monitoring — Metrics Aggregator
=============================================

Collects real-time metrics from the 7 existing collections.
No new collections needed — all metrics computed on-the-fly.

Health Domains:
  1. Provider Health
  2. Ingest Pipeline Health
  3. ARI Push Engine Health
  4. Reconciliation Health
  5. Queue & Worker Health
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.tenant_db import get_system_db
from domains.channel_manager.data_model import (
    COLL_ARI_CHANGE_SETS,
    COLL_ARI_DRIFT_STATE,
    COLL_ARI_OUTBOUND_LOGS,
    COLL_PROVIDER_CONNECTIONS,
    COLL_RAW_CHANNEL_EVENTS,
    COLL_RECONCILIATION_CASES,
)

logger = logging.getLogger("monitoring.aggregator")

# Operational monitoring is system-level: it must read across ALL tenants
# (zero-fill counts, cross-tenant rollup). Using the tenant-aware proxy here
# would silently inject a tenant_id filter inherited from any background task
# that ran with set_tenant_context() (e.g. cache_warmer at startup), which
# was producing false-positive "critical" rollups when the active tenant had
# no recent ingest/recon activity. get_system_db() returns the raw, unscoped
# database — exactly what aggregate-style observability needs.
db = get_system_db()

_NO_ID = {"_id": 0}


async def collect_provider_health() -> dict[str, Any]:
    """Track provider connectivity and response success."""
    providers = {}
    connections = (
        await db[COLL_PROVIDER_CONNECTIONS]
        .find(
            {},
            _NO_ID,
        )
        .to_list(100)
    )

    for conn in connections:
        provider = conn.get("provider", "unknown")
        if provider not in providers:
            providers[provider] = {
                "connection_count": 0,
                "active_count": 0,
                "error_count": 0,
                "total_syncs": 0,
                "total_errors": 0,
                "consecutive_failures": 0,
                "last_successful_sync": None,
                "status": "unknown",
                "auth_failures": 0,
            }
        p = providers[provider]
        p["connection_count"] += 1

        status = conn.get("status", "")
        if status == "active":
            p["active_count"] += 1
        elif status == "error":
            p["error_count"] += 1

        p["total_syncs"] += conn.get("total_syncs", 0)
        p["total_errors"] += conn.get("total_errors", 0)
        p["consecutive_failures"] = max(p["consecutive_failures"], conn.get("consecutive_failures", 0))

        last_sync = conn.get("last_successful_sync")
        if last_sync and (not p["last_successful_sync"] or last_sync > p["last_successful_sync"]):
            p["last_successful_sync"] = last_sync

    for name, p in providers.items():
        if p["active_count"] > 0 and p["consecutive_failures"] < 3:
            p["status"] = "healthy"
        elif p["consecutive_failures"] >= 3:
            p["status"] = "critical"
        elif p["error_count"] > 0:
            p["status"] = "degraded"
        else:
            p["status"] = "inactive"

        total = p["total_syncs"] + p["total_errors"]
        p["api_error_rate"] = round(p["total_errors"] / max(total, 1) * 100, 2)

    return {
        "providers": providers,
        "total_connections": len(connections),
        "active_connections": sum(1 for c in connections if c.get("status") == "active"),
    }


async def collect_ingest_health() -> dict[str, Any]:
    """Monitor the reservation ingest pipeline."""
    now = datetime.now(UTC)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Status breakdown
    status_pipeline = [
        {"$group": {"_id": "$processing_status", "count": {"$sum": 1}}},
    ]
    status_counts: dict[str, int] = {}
    async for doc in db[COLL_RAW_CHANNEL_EVENTS].aggregate(status_pipeline):
        status_counts[doc["_id"]] = doc["count"]

    total = sum(status_counts.values())

    # Recent events (last hour)
    recent_count = await db[COLL_RAW_CHANNEL_EVENTS].count_documents(
        {"received_at": {"$gte": one_hour_ago}},
    )

    # Failed in last day
    failed_recent = await db[COLL_RAW_CHANNEL_EVENTS].count_documents(
        {"processing_status": "failed", "received_at": {"$gte": one_day_ago}},
    )

    # Pending count
    pending = status_counts.get("pending", 0)

    # Duplicate rate
    duplicates = status_counts.get("duplicate", 0)
    duplicate_rate = round(duplicates / max(total, 1) * 100, 2)

    # Stale rate
    stale = status_counts.get("stale", 0)
    stale_rate = round(stale / max(total, 1) * 100, 2)

    processed = status_counts.get("processed", 0)
    failed = status_counts.get("failed", 0)

    # Pre-insert dedup guard counter — catchup short-circuits.
    # See `monitoring/dedup_counter.py`. Redis-backed sliding window
    # (shared across instances + restart-safe) with per-process
    # in-memory fallback when Redis is unavailable.
    from .dedup_counter import get_counts as _dedup_get_counts

    try:
        dedup = await _dedup_get_counts()
    except Exception as e:
        logger.warning(f"dedup counter read failed: {e}")
        dedup = {
            "last_1h_total": 0,
            "last_24h_total": 0,
            "last_1h_by_tenant_provider": {},
            "last_24h_by_tenant_provider": {},
        }

    return {
        "total_events": total,
        "pending": pending,
        "processed": processed,
        "failed": failed,
        "duplicates": duplicates,
        "stale": stale,
        "recent_events_1h": recent_count,
        "failed_recent_24h": failed_recent,
        "duplicate_rate": duplicate_rate,
        "stale_rate": stale_rate,
        "catchup_dedup_skips_1h": dedup["last_1h_total"],
        "catchup_dedup_skips_24h": dedup["last_24h_total"],
        "catchup_dedup_by_tenant_1h": dedup["last_1h_by_tenant_provider"],
        "catchup_dedup_by_tenant_24h": dedup["last_24h_by_tenant_provider"],
        "status": "healthy" if failed_recent < 5 and pending < 100 else ("critical" if failed_recent > 20 or pending > 500 else "degraded"),
    }


async def collect_ari_health() -> dict[str, Any]:
    """Monitor outbound ARI synchronization."""
    now = datetime.now(UTC)
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Outbound logs (last 24h)
    recent_logs = (
        await db[COLL_ARI_OUTBOUND_LOGS]
        .find(
            {"created_at": {"$gte": one_day_ago}},
            _NO_ID,
        )
        .to_list(1000)
    )

    total_pushes = len(recent_logs)
    success_count = sum(1 for entry in recent_logs if entry.get("status") == "success" or entry.get("success"))
    error_count = total_pushes - success_count

    latencies = [entry.get("duration_ms", 0) for entry in recent_logs if entry.get("duration_ms")]
    latencies.sort()

    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

    # Pending change sets
    pending_changesets = await db[COLL_ARI_CHANGE_SETS].count_documents(
        {"status": {"$in": ["pending", "queued"]}},
    )

    # Drift state
    drift_count = await db[COLL_ARI_DRIFT_STATE].count_documents(
        {"has_drift": True},
    )

    success_rate = round(success_count / max(total_pushes, 1) * 100, 2)

    # No activity in the last 24h (fresh tenant or quiet period) is NOT a
    # failure signal. Without this guard, success_rate=0 from zero-fill
    # would always trip "<80 → critical" and the rollup would stay red
    # forever on any otel that hasn't pushed yet. Mirrors how
    # collect_ingest_health treats total_events=0. drift_count is included
    # so that an ARI that is silent BUT carrying drift still surfaces as
    # degraded — silence alone is not a clean bill of health.
    if total_pushes == 0 and pending_changesets == 0 and drift_count == 0:
        status = "healthy"
    elif success_rate >= 95 and pending_changesets < 50:
        status = "healthy"
    elif success_rate < 80 or pending_changesets > 200:
        status = "critical"
    else:
        status = "degraded"

    return {
        "total_pushes_24h": total_pushes,
        "success_count": success_count,
        "error_count": error_count,
        "success_rate": success_rate,
        "error_rate": round(100 - success_rate, 2),
        "latency_p50": p50,
        "latency_p95": p95,
        "latency_p99": p99,
        "pending_changesets": pending_changesets,
        "drift_count": drift_count,
        "status": status,
    }


async def collect_reconciliation_health() -> dict[str, Any]:
    """Track mismatch trends."""
    # Open cases
    open_q = {"status": {"$in": ["open", "acknowledged"]}}

    type_pipeline = [
        {"$match": open_q},
        {"$group": {"_id": "$case_type", "count": {"$sum": 1}}},
    ]
    by_type: dict[str, int] = {}
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(type_pipeline):
        by_type[doc["_id"]] = doc["count"]

    severity_pipeline = [
        {"$match": open_q},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    by_severity: dict[str, int] = {}
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(severity_pipeline):
        by_severity[doc["_id"]] = doc["count"]

    total_open = sum(by_type.values())

    # Growth rate (cases created in last 24h)
    one_day_ago = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    recent_cases = await db[COLL_RECONCILIATION_CASES].count_documents(
        {"created_at": {"$gte": one_day_ago}},
    )

    critical_count = by_severity.get("critical", 0)

    return {
        "open_cases": total_open,
        "cases_by_type": by_type,
        "cases_by_severity": by_severity,
        "case_growth_rate_24h": recent_cases,
        "critical_count": critical_count,
        "status": "healthy" if critical_count == 0 and total_open < 10 else ("critical" if critical_count > 0 or total_open > 50 else "degraded"),
    }


async def collect_queue_worker_health() -> dict[str, Any]:
    """Monitor background workers."""
    from domains.channel_manager.ingest.workers import get_worker_states
    from domains.channel_manager.reconciliation_engine.reconciliation_worker import get_reconciliation_worker_state

    worker_states = get_worker_states()
    recon_state = get_reconciliation_worker_state()

    now = datetime.now(UTC)
    stalled_workers = []
    worker_details = {}

    for name, state in worker_states.items():
        last_run = state.get("last_run")
        interval = state.get("interval_seconds", 600)

        is_stalled = False
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                age_seconds = (now - last_dt).total_seconds()
                is_stalled = age_seconds > interval * 3
            except (ValueError, TypeError):
                pass

        if is_stalled:
            stalled_workers.append(name)

        worker_details[name] = {
            "running": state.get("running", False),
            "last_run": last_run,
            "interval_seconds": interval,
            "is_stalled": is_stalled,
            "errors": state.get("errors", 0),
        }

    # Reconciliation worker
    recon_last = recon_state.get("last_run")
    recon_stalled = False
    if recon_last:
        try:
            last_dt = datetime.fromisoformat(recon_last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
            recon_stalled = (now - last_dt).total_seconds() > 3600
        except (ValueError, TypeError):
            pass

    worker_details["reconciliation_worker"] = {
        "running": recon_state.get("running", False),
        "last_run": recon_last,
        "interval_seconds": recon_state.get("interval_seconds", 900),
        "is_stalled": recon_stalled,
        "runs_total": recon_state.get("runs_total", 0),
    }

    if recon_stalled:
        stalled_workers.append("reconciliation_worker")

    # Queue depth (pending events)
    pending_events = await db[COLL_RAW_CHANNEL_EVENTS].count_documents(
        {"processing_status": "pending"},
    )
    failed_events = await db[COLL_RAW_CHANNEL_EVENTS].count_documents(
        {"processing_status": "failed"},
    )

    return {
        "workers": worker_details,
        "stalled_workers": stalled_workers,
        "queue_depth": pending_events,
        "retry_backlog": failed_events,
        "dead_letter_events": 0,
        "status": "healthy" if not stalled_workers and pending_events < 100 else ("critical" if len(stalled_workers) > 0 or pending_events > 500 else "degraded"),
    }


async def collect_all_metrics() -> dict[str, Any]:
    """Aggregate all health domain metrics."""
    provider = await collect_provider_health()
    ingest = await collect_ingest_health()
    ari = await collect_ari_health()
    recon = await collect_reconciliation_health()
    queue = await collect_queue_worker_health()

    statuses = [provider.get("providers", {}).get(p, {}).get("status", "unknown") for p in provider.get("providers", {})]
    statuses.extend(
        [
            ingest.get("status", "unknown"),
            ari.get("status", "unknown"),
            recon.get("status", "unknown"),
            queue.get("status", "unknown"),
        ]
    )

    if "critical" in statuses:
        system_health = "critical"
    elif "degraded" in statuses:
        system_health = "degraded"
    elif all(s in ("healthy", "unknown", "inactive") for s in statuses):
        system_health = "healthy"
    else:
        system_health = "unknown"

    return {
        "system_health": system_health,
        "collected_at": datetime.now(UTC).isoformat(),
        "provider_health": provider,
        "ingest_health": ingest,
        "ari_health": ari,
        "reconciliation_health": recon,
        "queue_health": queue,
    }
