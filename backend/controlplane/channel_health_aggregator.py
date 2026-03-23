"""
Channel Health Aggregator — Computes channel-level health metrics for Control Plane.

Metrics:
  - Push latency percentiles (p50 / p95 / p99) per provider
  - Sync success rate (%) per provider
  - Failure breakdown (timeout / validation / mapping / auth / provider)
  - Reconciliation drift count per provider
  - Retry success rate per provider
  - Provider-based SLA compliance
"""
import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import db

logger = logging.getLogger("controlplane.channel_health_aggregator")

RATE_PUSH_METRICS = "cm_rate_push_metrics"
CONNECTORS = "cm_connectors"
SYNC_JOBS = "cm_sync_jobs"
RECONCILIATION_ISSUES = "cm_reconciliation_issues"

# SLA targets
SLA_PUSH_LATENCY_P95_MS = 5000
SLA_SYNC_SUCCESS_RATE = 95.0
SLA_RETRY_SUCCESS_RATE = 80.0


async def compute_channel_health(
    tenant_id: Optional[str] = None, hours: int = 24,
) -> Dict[str, Any]:
    """Top-level aggregation for the Channel Health tab."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=hours)).isoformat()

    results = await asyncio.gather(
        _push_latency_percentiles(tenant_id, cutoff),
        _sync_metrics_by_provider(tenant_id, cutoff),
        _failure_breakdown(tenant_id, cutoff),
        _reconciliation_drift(tenant_id),
        _retry_metrics(tenant_id, cutoff),
        _provider_summary(tenant_id),
        return_exceptions=True,
    )

    latency = results[0] if not isinstance(results[0], Exception) else {}
    sync_m = results[1] if not isinstance(results[1], Exception) else {}
    failures = results[2] if not isinstance(results[2], Exception) else {}
    drift = results[3] if not isinstance(results[3], Exception) else {}
    retries = results[4] if not isinstance(results[4], Exception) else {}
    providers = results[5] if not isinstance(results[5], Exception) else {}

    # Build per-provider SLA
    provider_sla = _compute_sla(latency, sync_m, retries)

    return {
        "push_latency": latency,
        "sync_metrics": sync_m,
        "failure_breakdown": failures,
        "reconciliation_drift": drift,
        "retry_metrics": retries,
        "provider_summary": providers,
        "provider_sla": provider_sla,
        "period_hours": hours,
        "calculated_at": now.isoformat(),
    }


async def _push_latency_percentiles(
    tenant_id: Optional[str], cutoff: str,
) -> Dict[str, Any]:
    """Compute p50/p95/p99 push latency per provider and overall."""
    match: Dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "success": True}
    if tenant_id:
        match["tenant_id"] = tenant_id

    # Get all successful push latencies grouped by provider
    pipeline = [
        {"$match": match},
        {"$lookup": {
            "from": CONNECTORS,
            "let": {"cid": "$connector_id", "tid": "$tenant_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$id", "$$cid"]},
                    {"$eq": ["$tenant_id", "$$tid"]},
                ]}}},
                {"$project": {"_id": 0, "provider": 1}},
            ],
            "as": "_conn",
        }},
        {"$addFields": {"provider": {"$ifNull": [{"$arrayElemAt": ["$_conn.provider", 0]}, "unknown"]}}},
        {"$group": {
            "_id": "$provider",
            "latencies": {"$push": "$latency_ms"},
            "count": {"$sum": 1},
        }},
    ]

    results: Dict[str, Any] = {"overall": {}, "by_provider": {}}
    all_latencies: List[int] = []

    try:
        async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
            provider = doc["_id"] or "unknown"
            lats = sorted(doc["latencies"])
            all_latencies.extend(lats)
            results["by_provider"][provider] = {
                "p50": _percentile(lats, 50),
                "p95": _percentile(lats, 95),
                "p99": _percentile(lats, 99),
                "count": doc["count"],
                "avg": round(sum(lats) / max(len(lats), 1)),
                "min": lats[0] if lats else 0,
                "max": lats[-1] if lats else 0,
            }
    except Exception as e:
        logger.warning("Push latency aggregation error: %s", e)

    if all_latencies:
        all_latencies.sort()
        results["overall"] = {
            "p50": _percentile(all_latencies, 50),
            "p95": _percentile(all_latencies, 95),
            "p99": _percentile(all_latencies, 99),
            "count": len(all_latencies),
            "avg": round(sum(all_latencies) / len(all_latencies)),
        }
    else:
        results["overall"] = {"p50": 0, "p95": 0, "p99": 0, "count": 0, "avg": 0}

    return results


async def _sync_metrics_by_provider(
    tenant_id: Optional[str], cutoff: str,
) -> Dict[str, Any]:
    """Sync success rate per provider."""
    match: Dict[str, Any] = {"started_at": {"$gte": cutoff}}
    if tenant_id:
        match["tenant_id"] = tenant_id

    pipeline = [
        {"$match": match},
        {"$lookup": {
            "from": CONNECTORS,
            "let": {"cid": "$connector_id", "tid": "$tenant_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$id", "$$cid"]},
                    {"$eq": ["$tenant_id", "$$tid"]},
                ]}}},
                {"$project": {"_id": 0, "provider": 1}},
            ],
            "as": "_conn",
        }},
        {"$addFields": {"provider": {"$ifNull": [{"$arrayElemAt": ["$_conn.provider", 0]}, "unknown"]}}},
        {"$group": {
            "_id": "$provider",
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "avg_duration": {"$avg": "$duration_ms"},
        }},
    ]

    results: Dict[str, Any] = {"by_provider": {}, "overall": {}}
    total_all = 0
    completed_all = 0

    try:
        async for doc in db[SYNC_JOBS].aggregate(pipeline):
            provider = doc["_id"] or "unknown"
            t = doc["total"]
            c = doc["completed"]
            rate = round(c / max(t, 1) * 100, 1)
            total_all += t
            completed_all += c
            results["by_provider"][provider] = {
                "total": t,
                "completed": c,
                "failed": doc["failed"],
                "success_rate": rate,
                "avg_duration_ms": round(doc.get("avg_duration") or 0),
            }
    except Exception as e:
        logger.warning("Sync metrics aggregation error: %s", e)

    results["overall"] = {
        "total": total_all,
        "completed": completed_all,
        "success_rate": round(completed_all / max(total_all, 1) * 100, 1),
    }

    return results


async def _failure_breakdown(
    tenant_id: Optional[str], cutoff: str,
) -> Dict[str, Any]:
    """Failure breakdown by classification (timeout/validation/mapping etc.)."""
    match: Dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "success": False}
    if tenant_id:
        match["tenant_id"] = tenant_id

    pipeline = [
        {"$match": match},
        {"$lookup": {
            "from": CONNECTORS,
            "let": {"cid": "$connector_id", "tid": "$tenant_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$id", "$$cid"]},
                    {"$eq": ["$tenant_id", "$$tid"]},
                ]}}},
                {"$project": {"_id": 0, "provider": 1}},
            ],
            "as": "_conn",
        }},
        {"$addFields": {"provider": {"$ifNull": [{"$arrayElemAt": ["$_conn.provider", 0]}, "unknown"]}}},
        {"$group": {
            "_id": {"provider": "$provider", "classification": "$failure_classification"},
            "count": {"$sum": 1},
        }},
    ]

    results: Dict[str, Any] = {"by_provider": {}, "overall": {}}
    overall_counts: Dict[str, int] = {}

    try:
        async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
            provider = doc["_id"]["provider"] or "unknown"
            classification = doc["_id"]["classification"] or "unknown"
            count = doc["count"]

            if provider not in results["by_provider"]:
                results["by_provider"][provider] = {}
            results["by_provider"][provider][classification] = count
            overall_counts[classification] = overall_counts.get(classification, 0) + count
    except Exception as e:
        logger.warning("Failure breakdown aggregation error: %s", e)

    results["overall"] = overall_counts
    results["total_failures"] = sum(overall_counts.values())

    return results


async def _reconciliation_drift(
    tenant_id: Optional[str],
) -> Dict[str, Any]:
    """Open reconciliation issues (drift) per provider."""
    match: Dict[str, Any] = {"status": {"$in": ["open", "investigating", "retrying"]}}
    if tenant_id:
        match["tenant_id"] = tenant_id

    pipeline = [
        {"$match": match},
        {"$lookup": {
            "from": CONNECTORS,
            "let": {"cid": "$connector_id", "tid": "$tenant_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$id", "$$cid"]},
                    {"$eq": ["$tenant_id", "$$tid"]},
                ]}}},
                {"$project": {"_id": 0, "provider": 1}},
            ],
            "as": "_conn",
        }},
        {"$addFields": {"provider": {"$ifNull": [{"$arrayElemAt": ["$_conn.provider", 0]}, "unknown"]}}},
        {"$group": {
            "_id": {"provider": "$provider", "issue_type": "$issue_type"},
            "count": {"$sum": 1},
        }},
    ]

    results: Dict[str, Any] = {"by_provider": {}, "total_open": 0}

    try:
        async for doc in db[RECONCILIATION_ISSUES].aggregate(pipeline):
            provider = doc["_id"]["provider"] or "unknown"
            issue_type = doc["_id"]["issue_type"] or "unknown"
            count = doc["count"]

            if provider not in results["by_provider"]:
                results["by_provider"][provider] = {"total": 0, "by_type": {}}
            results["by_provider"][provider]["by_type"][issue_type] = count
            results["by_provider"][provider]["total"] += count
            results["total_open"] += count
    except Exception as e:
        logger.warning("Reconciliation drift aggregation error: %s", e)

    return results


async def _retry_metrics(
    tenant_id: Optional[str], cutoff: str,
) -> Dict[str, Any]:
    """Retry success rate — pushes with retry_count > 0 that eventually succeeded."""
    match: Dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "retry_count": {"$gt": 0}}
    if tenant_id:
        match["tenant_id"] = tenant_id

    pipeline = [
        {"$match": match},
        {"$lookup": {
            "from": CONNECTORS,
            "let": {"cid": "$connector_id", "tid": "$tenant_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$id", "$$cid"]},
                    {"$eq": ["$tenant_id", "$$tid"]},
                ]}}},
                {"$project": {"_id": 0, "provider": 1}},
            ],
            "as": "_conn",
        }},
        {"$addFields": {"provider": {"$ifNull": [{"$arrayElemAt": ["$_conn.provider", 0]}, "unknown"]}}},
        {"$group": {
            "_id": "$provider",
            "total_retried": {"$sum": 1},
            "retried_success": {"$sum": {"$cond": ["$success", 1, 0]}},
            "total_retry_count": {"$sum": "$retry_count"},
        }},
    ]

    results: Dict[str, Any] = {"by_provider": {}, "overall": {}}
    total_retried = 0
    total_retried_success = 0

    try:
        async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
            provider = doc["_id"] or "unknown"
            t = doc["total_retried"]
            s = doc["retried_success"]
            total_retried += t
            total_retried_success += s
            results["by_provider"][provider] = {
                "total_retried": t,
                "retried_success": s,
                "retry_success_rate": round(s / max(t, 1) * 100, 1),
                "total_retry_count": doc["total_retry_count"],
            }
    except Exception as e:
        logger.warning("Retry metrics aggregation error: %s", e)

    results["overall"] = {
        "total_retried": total_retried,
        "retried_success": total_retried_success,
        "retry_success_rate": round(total_retried_success / max(total_retried, 1) * 100, 1),
    }

    return results


async def _provider_summary(
    tenant_id: Optional[str],
) -> Dict[str, Any]:
    """Quick summary of active connectors per provider."""
    match: Dict[str, Any] = {}
    if tenant_id:
        match["tenant_id"] = tenant_id

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$provider",
            "total": {"$sum": 1},
            "active": {"$sum": {"$cond": [{"$eq": ["$status", "active"]}, 1, 0]}},
            "inactive": {"$sum": {"$cond": [{"$ne": ["$status", "active"]}, 1, 0]}},
        }},
    ]

    results: Dict[str, Any] = {}
    try:
        async for doc in db[CONNECTORS].aggregate(pipeline):
            provider = doc["_id"] or "unknown"
            results[provider] = {
                "total": doc["total"],
                "active": doc["active"],
                "inactive": doc["inactive"],
            }
    except Exception as e:
        logger.warning("Provider summary aggregation error: %s", e)

    return results


def _compute_sla(
    latency: Dict[str, Any],
    sync_m: Dict[str, Any],
    retries: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute SLA compliance per provider."""
    providers = set()
    providers.update(latency.get("by_provider", {}).keys())
    providers.update(sync_m.get("by_provider", {}).keys())
    providers.update(retries.get("by_provider", {}).keys())

    sla: Dict[str, Any] = {}
    for prov in providers:
        lat = latency.get("by_provider", {}).get(prov, {})
        syn = sync_m.get("by_provider", {}).get(prov, {})
        ret = retries.get("by_provider", {}).get(prov, {})

        p95 = lat.get("p95", 0)
        sync_rate = syn.get("success_rate", 100.0)
        retry_rate = ret.get("retry_success_rate", 100.0)

        latency_ok = p95 <= SLA_PUSH_LATENCY_P95_MS
        sync_ok = sync_rate >= SLA_SYNC_SUCCESS_RATE
        retry_ok = retry_rate >= SLA_RETRY_SUCCESS_RATE

        compliant_count = sum([latency_ok, sync_ok, retry_ok])
        overall = "compliant" if compliant_count == 3 else ("warning" if compliant_count >= 2 else "breached")

        sla[prov] = {
            "push_latency_p95_ms": p95,
            "push_latency_target_ms": SLA_PUSH_LATENCY_P95_MS,
            "push_latency_ok": latency_ok,
            "sync_success_rate": sync_rate,
            "sync_target": SLA_SYNC_SUCCESS_RATE,
            "sync_ok": sync_ok,
            "retry_success_rate": retry_rate,
            "retry_target": SLA_RETRY_SUCCESS_RATE,
            "retry_ok": retry_ok,
            "overall": overall,
        }

    return sla


def _percentile(sorted_values: List[int], pct: int) -> int:
    """Compute percentile from a pre-sorted list."""
    if not sorted_values:
        return 0
    n = len(sorted_values)
    idx = (pct / 100) * (n - 1)
    lower = int(math.floor(idx))
    upper = int(math.ceil(idx))
    if lower == upper:
        return sorted_values[lower]
    frac = idx - lower
    return round(sorted_values[lower] * (1 - frac) + sorted_values[upper] * frac)
