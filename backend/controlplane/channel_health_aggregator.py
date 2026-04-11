"""
Channel Health Aggregator — Computes channel-level health metrics for Control Plane.

Metrics:
  - Push latency percentiles (p50 / p95 / p99) per provider
  - Sync success rate (%) per provider
  - Failure breakdown (timeout / validation / mapping / auth / provider)
  - Reconciliation drift count per provider
  - Retry success rate per provider
  - Provider-based SLA compliance
  - Historical trends (time-bucketed)
  - Field KPIs (period-over-period comparison, MTTR, operator interventions)
  - Weekly proof (week-over-week improvement summary)
"""
import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

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
    tenant_id: str | None = None, hours: int = 24,
) -> dict[str, Any]:
    """Top-level aggregation for the Channel Health tab."""
    now = datetime.now(UTC)
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


# ─── Historical Trends ───────────────────────────────────────────

async def compute_channel_health_trends(
    tenant_id: str | None = None,
    hours: int = 168,
    bucket_hours: int = 0,
) -> dict[str, Any]:
    """Time-bucketed historical trends for channel health metrics."""
    now = datetime.now(UTC)
    cutoff = (now - timedelta(hours=hours)).isoformat()

    if bucket_hours <= 0:
        bucket_hours = 1 if hours <= 24 else (4 if hours <= 72 else (12 if hours <= 168 else 24))

    results = await asyncio.gather(
        _trend_push_latency(tenant_id, cutoff, bucket_hours),
        _trend_sync_success(tenant_id, cutoff, bucket_hours),
        _trend_failures(tenant_id, cutoff, bucket_hours),
        _trend_drift_created(tenant_id, cutoff, bucket_hours),
        _trend_retry_success(tenant_id, cutoff, bucket_hours),
        return_exceptions=True,
    )

    latency_buckets = results[0] if not isinstance(results[0], Exception) else []
    sync_buckets = results[1] if not isinstance(results[1], Exception) else []
    failure_buckets = results[2] if not isinstance(results[2], Exception) else []
    drift_buckets = results[3] if not isinstance(results[3], Exception) else []
    retry_buckets = results[4] if not isinstance(results[4], Exception) else []

    ts_map: dict[str, dict[str, Any]] = {}
    for b in latency_buckets:
        ts_map.setdefault(b["t"], {})["push_latency"] = {"p50": b["p50"], "p95": b["p95"], "p99": b["p99"], "count": b["count"]}
    for b in sync_buckets:
        ts_map.setdefault(b["t"], {})["sync"] = {"success_rate": b["success_rate"], "total": b["total"], "completed": b["completed"]}
    for b in failure_buckets:
        ts_map.setdefault(b["t"], {})["failures"] = b["count"]
    for b in drift_buckets:
        ts_map.setdefault(b["t"], {})["drift_created"] = b["count"]
    for b in retry_buckets:
        ts_map.setdefault(b["t"], {})["retry"] = {"success_rate": b["success_rate"], "total": b["total"]}

    buckets = []
    for ts in sorted(ts_map.keys()):
        entry = {"timestamp": ts, **ts_map[ts]}
        entry.setdefault("push_latency", {"p50": 0, "p95": 0, "p99": 0, "count": 0})
        entry.setdefault("sync", {"success_rate": 0, "total": 0, "completed": 0})
        entry.setdefault("failures", 0)
        entry.setdefault("drift_created", 0)
        entry.setdefault("retry", {"success_rate": 0, "total": 0})
        buckets.append(entry)

    return {
        "buckets": buckets,
        "bucket_size_hours": bucket_hours,
        "period_hours": hours,
        "total_buckets": len(buckets),
        "calculated_at": now.isoformat(),
    }


async def _trend_push_latency(tenant_id: str | None, cutoff: str, bucket_hours: int) -> list[dict]:
    match: dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "success": True}
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [
        {"$match": match},
        {"$addFields": {
            "_ts": {"$dateFromString": {"dateString": "$recorded_at", "onError": None}},
        }},
        {"$match": {"_ts": {"$ne": None}}},
        {"$addFields": {
            "_bucket": {"$dateTrunc": {"date": "$_ts", "unit": "hour", "binSize": bucket_hours}},
        }},
        {"$group": {
            "_id": "$_bucket",
            "latencies": {"$push": "$latency_ms"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    result = []
    try:
        async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
            lats = sorted(doc["latencies"])
            result.append({
                "t": doc["_id"].isoformat() if doc["_id"] else "",
                "p50": _percentile(lats, 50),
                "p95": _percentile(lats, 95),
                "p99": _percentile(lats, 99),
                "count": doc["count"],
            })
    except Exception as e:
        logger.warning("Trend push latency error: %s", e)
    return result


async def _trend_sync_success(tenant_id: str | None, cutoff: str, bucket_hours: int) -> list[dict]:
    match: dict[str, Any] = {"started_at": {"$gte": cutoff}}
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [
        {"$match": match},
        {"$addFields": {
            "_ts": {"$dateFromString": {"dateString": "$started_at", "onError": None}},
        }},
        {"$match": {"_ts": {"$ne": None}}},
        {"$addFields": {
            "_bucket": {"$dateTrunc": {"date": "$_ts", "unit": "hour", "binSize": bucket_hours}},
        }},
        {"$group": {
            "_id": "$_bucket",
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    result = []
    try:
        async for doc in db[SYNC_JOBS].aggregate(pipeline):
            t = doc["total"]
            c = doc["completed"]
            result.append({
                "t": doc["_id"].isoformat() if doc["_id"] else "",
                "success_rate": round(c / max(t, 1) * 100, 1),
                "total": t,
                "completed": c,
            })
    except Exception as e:
        logger.warning("Trend sync success error: %s", e)
    return result


async def _trend_failures(tenant_id: str | None, cutoff: str, bucket_hours: int) -> list[dict]:
    match: dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "success": False}
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [
        {"$match": match},
        {"$addFields": {
            "_ts": {"$dateFromString": {"dateString": "$recorded_at", "onError": None}},
        }},
        {"$match": {"_ts": {"$ne": None}}},
        {"$addFields": {
            "_bucket": {"$dateTrunc": {"date": "$_ts", "unit": "hour", "binSize": bucket_hours}},
        }},
        {"$group": {"_id": "$_bucket", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    result = []
    try:
        async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
            result.append({"t": doc["_id"].isoformat() if doc["_id"] else "", "count": doc["count"]})
    except Exception as e:
        logger.warning("Trend failures error: %s", e)
    return result


async def _trend_drift_created(tenant_id: str | None, cutoff: str, bucket_hours: int) -> list[dict]:
    match: dict[str, Any] = {"detected_at": {"$gte": cutoff}}
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [
        {"$match": match},
        {"$addFields": {
            "_ts": {"$dateFromString": {"dateString": "$detected_at", "onError": None}},
        }},
        {"$match": {"_ts": {"$ne": None}}},
        {"$addFields": {
            "_bucket": {"$dateTrunc": {"date": "$_ts", "unit": "hour", "binSize": bucket_hours}},
        }},
        {"$group": {"_id": "$_bucket", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    result = []
    try:
        async for doc in db[RECONCILIATION_ISSUES].aggregate(pipeline):
            result.append({"t": doc["_id"].isoformat() if doc["_id"] else "", "count": doc["count"]})
    except Exception as e:
        logger.warning("Trend drift created error: %s", e)
    return result


async def _trend_retry_success(tenant_id: str | None, cutoff: str, bucket_hours: int) -> list[dict]:
    match: dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "retry_count": {"$gt": 0}}
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [
        {"$match": match},
        {"$addFields": {
            "_ts": {"$dateFromString": {"dateString": "$recorded_at", "onError": None}},
        }},
        {"$match": {"_ts": {"$ne": None}}},
        {"$addFields": {
            "_bucket": {"$dateTrunc": {"date": "$_ts", "unit": "hour", "binSize": bucket_hours}},
        }},
        {"$group": {
            "_id": "$_bucket",
            "total": {"$sum": 1},
            "success": {"$sum": {"$cond": ["$success", 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    result = []
    try:
        async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
            t = doc["total"]
            s = doc["success"]
            result.append({
                "t": doc["_id"].isoformat() if doc["_id"] else "",
                "success_rate": round(s / max(t, 1) * 100, 1),
                "total": t,
            })
    except Exception as e:
        logger.warning("Trend retry success error: %s", e)
    return result


# ─── Field KPIs ──────────────────────────────────────────────────

async def compute_field_kpis(
    tenant_id: str | None = None,
    period_hours: int = 24,
) -> dict[str, Any]:
    """Operational field KPIs with period-over-period comparison."""
    now = datetime.now(UTC)
    current_cutoff = (now - timedelta(hours=period_hours)).isoformat()
    prev_cutoff = (now - timedelta(hours=period_hours * 2)).isoformat()

    results = await asyncio.gather(
        _kpi_sync_success(tenant_id, current_cutoff, prev_cutoff, current_cutoff),
        _kpi_drift(tenant_id, current_cutoff, prev_cutoff, current_cutoff),
        _kpi_mttr(tenant_id, current_cutoff, prev_cutoff, current_cutoff),
        _kpi_operator_interventions(tenant_id, current_cutoff, prev_cutoff, current_cutoff),
        _kpi_push_sla(tenant_id, current_cutoff, prev_cutoff, current_cutoff),
        return_exceptions=True,
    )

    sync_kpi = results[0] if not isinstance(results[0], Exception) else _empty_kpi()
    drift_kpi = results[1] if not isinstance(results[1], Exception) else _empty_kpi()
    mttr_kpi = results[2] if not isinstance(results[2], Exception) else _empty_kpi()
    operator_kpi = results[3] if not isinstance(results[3], Exception) else _empty_kpi()
    sla_kpi = results[4] if not isinstance(results[4], Exception) else _empty_kpi()

    return {
        "sync_success": sync_kpi,
        "drift_reduction": drift_kpi,
        "mttr_hours": mttr_kpi,
        "operator_interventions": operator_kpi,
        "push_sla_compliance": sla_kpi,
        "period_hours": period_hours,
        "calculated_at": now.isoformat(),
    }


def _empty_kpi() -> dict[str, Any]:
    return {"current": 0, "previous": 0, "delta": 0, "trend": "flat"}


def _kpi_trend(current: float, previous: float) -> str:
    if current > previous:
        return "up"
    elif current < previous:
        return "down"
    return "flat"


async def _kpi_sync_success(tenant_id, current_cutoff, prev_cutoff, current_start) -> dict[str, Any]:
    async def _rate(cutoff_from, cutoff_to):
        match: dict[str, Any] = {"started_at": {"$gte": cutoff_from, "$lt": cutoff_to}}
        if tenant_id:
            match["tenant_id"] = tenant_id
        pipeline = [{"$match": match}, {"$group": {
            "_id": None, "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
        }}]
        try:
            async for doc in db[SYNC_JOBS].aggregate(pipeline):
                t = doc["total"]
                return round(doc["completed"] / max(t, 1) * 100, 1)
        except Exception:
            pass
        return 0.0

    current = await _rate(current_cutoff, datetime.now(UTC).isoformat())
    previous = await _rate(prev_cutoff, current_start)
    delta = round(current - previous, 1)
    return {"current": current, "previous": previous, "delta": delta, "trend": _kpi_trend(current, previous), "unit": "%"}


async def _kpi_drift(tenant_id, current_cutoff, prev_cutoff, current_start) -> dict[str, Any]:
    async def _count(cutoff_from, cutoff_to):
        match: dict[str, Any] = {"detected_at": {"$gte": cutoff_from, "$lt": cutoff_to}}
        if tenant_id:
            match["tenant_id"] = tenant_id
        try:
            return await db[RECONCILIATION_ISSUES].count_documents(match)
        except Exception:
            return 0

    current = await _count(current_cutoff, datetime.now(UTC).isoformat())
    previous = await _count(prev_cutoff, current_start)
    delta = current - previous
    return {"current": current, "previous": previous, "delta": delta, "trend": _kpi_trend(current, previous), "unit": "issues"}


async def _kpi_mttr(tenant_id, current_cutoff, prev_cutoff, current_start) -> dict[str, Any]:
    async def _avg_resolve_hours(cutoff_from, cutoff_to):
        match: dict[str, Any] = {
            "resolved_at": {"$gte": cutoff_from, "$lt": cutoff_to},
            "status": "resolved",
        }
        if tenant_id:
            match["tenant_id"] = tenant_id
        pipeline = [
            {"$match": match},
            {"$addFields": {
                "_det": {"$dateFromString": {"dateString": "$detected_at", "onError": None}},
                "_res": {"$dateFromString": {"dateString": "$resolved_at", "onError": None}},
            }},
            {"$match": {"_det": {"$ne": None}, "_res": {"$ne": None}}},
            {"$addFields": {"_dur_ms": {"$subtract": ["$_res", "$_det"]}}},
            {"$group": {"_id": None, "avg_ms": {"$avg": "$_dur_ms"}}},
        ]
        try:
            async for doc in db[RECONCILIATION_ISSUES].aggregate(pipeline):
                return round((doc["avg_ms"] or 0) / 3600000, 1)
        except Exception:
            pass
        return 0.0

    current = await _avg_resolve_hours(current_cutoff, datetime.now(UTC).isoformat())
    previous = await _avg_resolve_hours(prev_cutoff, current_start)
    delta = round(current - previous, 1)
    return {"current": current, "previous": previous, "delta": delta, "trend": _kpi_trend(current, previous), "unit": "saat"}


async def _kpi_operator_interventions(tenant_id, current_cutoff, prev_cutoff, current_start) -> dict[str, Any]:
    async def _count(cutoff_from, cutoff_to):
        match: dict[str, Any] = {
            "resolved_at": {"$gte": cutoff_from, "$lt": cutoff_to},
            "resolution_type": "manual",
        }
        if tenant_id:
            match["tenant_id"] = tenant_id
        try:
            return await db[RECONCILIATION_ISSUES].count_documents(match)
        except Exception:
            return 0

    current = await _count(current_cutoff, datetime.now(UTC).isoformat())
    previous = await _count(prev_cutoff, current_start)
    delta = current - previous
    return {"current": current, "previous": previous, "delta": delta, "trend": _kpi_trend(current, previous), "unit": "mudahale"}


async def _kpi_push_sla(tenant_id, current_cutoff, prev_cutoff, current_start) -> dict[str, Any]:
    async def _compliance_pct(cutoff_from, cutoff_to):
        match: dict[str, Any] = {"recorded_at": {"$gte": cutoff_from, "$lt": cutoff_to}, "success": True}
        if tenant_id:
            match["tenant_id"] = tenant_id
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "within_sla": {"$sum": {"$cond": [{"$lte": ["$latency_ms", SLA_PUSH_LATENCY_P95_MS]}, 1, 0]}},
            }},
        ]
        try:
            async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
                return round(doc["within_sla"] / max(doc["total"], 1) * 100, 1)
        except Exception:
            pass
        return 0.0

    current = await _compliance_pct(current_cutoff, datetime.now(UTC).isoformat())
    previous = await _compliance_pct(prev_cutoff, current_start)
    delta = round(current - previous, 1)
    return {"current": current, "previous": previous, "delta": delta, "trend": _kpi_trend(current, previous), "unit": "%"}


async def _push_latency_percentiles(
    tenant_id: str | None, cutoff: str,
) -> dict[str, Any]:
    """Compute p50/p95/p99 push latency per provider and overall."""
    match: dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "success": True}
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

    results: dict[str, Any] = {"overall": {}, "by_provider": {}}
    all_latencies: list[int] = []

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
    tenant_id: str | None, cutoff: str,
) -> dict[str, Any]:
    """Sync success rate per provider."""
    match: dict[str, Any] = {"started_at": {"$gte": cutoff}}
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

    results: dict[str, Any] = {"by_provider": {}, "overall": {}}
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
    tenant_id: str | None, cutoff: str,
) -> dict[str, Any]:
    """Failure breakdown by classification (timeout/validation/mapping etc.)."""
    match: dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "success": False}
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

    results: dict[str, Any] = {"by_provider": {}, "overall": {}}
    overall_counts: dict[str, int] = {}

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
    tenant_id: str | None,
) -> dict[str, Any]:
    """Open reconciliation issues (drift) per provider."""
    match: dict[str, Any] = {"status": {"$in": ["open", "investigating", "retrying"]}}
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

    results: dict[str, Any] = {"by_provider": {}, "total_open": 0}

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
    tenant_id: str | None, cutoff: str,
) -> dict[str, Any]:
    """Retry success rate — pushes with retry_count > 0 that eventually succeeded."""
    match: dict[str, Any] = {"recorded_at": {"$gte": cutoff}, "retry_count": {"$gt": 0}}
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

    results: dict[str, Any] = {"by_provider": {}, "overall": {}}
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
    tenant_id: str | None,
) -> dict[str, Any]:
    """Quick summary of active connectors per provider."""
    match: dict[str, Any] = {}
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

    results: dict[str, Any] = {}
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
    latency: dict[str, Any],
    sync_m: dict[str, Any],
    retries: dict[str, Any],
) -> dict[str, Any]:
    """Compute SLA compliance per provider."""
    providers = set()
    providers.update(latency.get("by_provider", {}).keys())
    providers.update(sync_m.get("by_provider", {}).keys())
    providers.update(retries.get("by_provider", {}).keys())

    sla: dict[str, Any] = {}
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


def _percentile(sorted_values: list[int], pct: int) -> int:
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


# ─── Weekly Proof — Week-over-week improvement ──────────────────

async def compute_weekly_proof(
    tenant_id: str | None = None,
    weeks: int = 8,
) -> dict[str, Any]:
    """Week-over-week summary for drift, MTTR, SLA compliance, sync success."""
    now = datetime.now(UTC)
    weekly_data = []

    for w in range(weeks - 1, -1, -1):
        week_end = now - timedelta(weeks=w)
        week_start = week_end - timedelta(weeks=1)
        start_iso = week_start.isoformat()
        end_iso = week_end.isoformat()

        results = await asyncio.gather(
            _weekly_sync_rate(tenant_id, start_iso, end_iso),
            _weekly_drift_count(tenant_id, start_iso, end_iso),
            _weekly_mttr(tenant_id, start_iso, end_iso),
            _weekly_sla_compliance(tenant_id, start_iso, end_iso),
            _weekly_push_p95(tenant_id, start_iso, end_iso),
            return_exceptions=True,
        )

        sync_rate = results[0] if not isinstance(results[0], Exception) else 0.0
        drift_count = results[1] if not isinstance(results[1], Exception) else 0
        mttr = results[2] if not isinstance(results[2], Exception) else 0.0
        sla_pct = results[3] if not isinstance(results[3], Exception) else 0.0
        push_p95 = results[4] if not isinstance(results[4], Exception) else 0

        weekly_data.append({
            "week_label": week_start.strftime("W%U"),
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": week_end.strftime("%Y-%m-%d"),
            "sync_success_rate": sync_rate,
            "drift_count": drift_count,
            "mttr_hours": mttr,
            "sla_compliance": sla_pct,
            "push_latency_p95": push_p95,
        })

    # Compute improvement deltas (first week vs last week)
    improvements = {}
    if len(weekly_data) >= 2:
        first = weekly_data[0]
        last = weekly_data[-1]
        improvements = {
            "sync_success_delta": round(last["sync_success_rate"] - first["sync_success_rate"], 1),
            "drift_delta": last["drift_count"] - first["drift_count"],
            "mttr_delta": round(last["mttr_hours"] - first["mttr_hours"], 1),
            "sla_delta": round(last["sla_compliance"] - first["sla_compliance"], 1),
            "push_p95_delta": last["push_latency_p95"] - first["push_latency_p95"],
        }

    return {
        "weeks": weekly_data,
        "improvements": improvements,
        "total_weeks": len(weekly_data),
        "calculated_at": now.isoformat(),
    }


async def _weekly_sync_rate(tenant_id: str | None, start: str, end: str) -> float:
    match: dict[str, Any] = {"started_at": {"$gte": start, "$lt": end}}
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [{"$match": match}, {"$group": {
        "_id": None, "total": {"$sum": 1},
        "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
    }}]
    try:
        async for doc in db[SYNC_JOBS].aggregate(pipeline):
            return round(doc["completed"] / max(doc["total"], 1) * 100, 1)
    except Exception:
        pass
    return 0.0


async def _weekly_drift_count(tenant_id: str | None, start: str, end: str) -> int:
    match: dict[str, Any] = {"detected_at": {"$gte": start, "$lt": end}}
    if tenant_id:
        match["tenant_id"] = tenant_id
    try:
        return await db[RECONCILIATION_ISSUES].count_documents(match)
    except Exception:
        return 0


async def _weekly_mttr(tenant_id: str | None, start: str, end: str) -> float:
    match: dict[str, Any] = {
        "resolved_at": {"$gte": start, "$lt": end},
        "status": "resolved",
    }
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [
        {"$match": match},
        {"$addFields": {
            "_det": {"$dateFromString": {"dateString": "$detected_at", "onError": None}},
            "_res": {"$dateFromString": {"dateString": "$resolved_at", "onError": None}},
        }},
        {"$match": {"_det": {"$ne": None}, "_res": {"$ne": None}}},
        {"$addFields": {"_dur_ms": {"$subtract": ["$_res", "$_det"]}}},
        {"$group": {"_id": None, "avg_ms": {"$avg": "$_dur_ms"}}},
    ]
    try:
        async for doc in db[RECONCILIATION_ISSUES].aggregate(pipeline):
            return round((doc["avg_ms"] or 0) / 3600000, 1)
    except Exception:
        pass
    return 0.0


async def _weekly_sla_compliance(tenant_id: str | None, start: str, end: str) -> float:
    match: dict[str, Any] = {"recorded_at": {"$gte": start, "$lt": end}, "success": True}
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "within_sla": {"$sum": {"$cond": [{"$lte": ["$latency_ms", SLA_PUSH_LATENCY_P95_MS]}, 1, 0]}},
        }},
    ]
    try:
        async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
            return round(doc["within_sla"] / max(doc["total"], 1) * 100, 1)
    except Exception:
        pass
    return 0.0


async def _weekly_push_p95(tenant_id: str | None, start: str, end: str) -> int:
    match: dict[str, Any] = {"recorded_at": {"$gte": start, "$lt": end}, "success": True}
    if tenant_id:
        match["tenant_id"] = tenant_id
    pipeline = [
        {"$match": match},
        {"$group": {"_id": None, "latencies": {"$push": "$latency_ms"}}},
    ]
    try:
        async for doc in db[RATE_PUSH_METRICS].aggregate(pipeline):
            lats = sorted(doc["latencies"])
            return _percentile(lats, 95)
    except Exception:
        pass
    return 0
