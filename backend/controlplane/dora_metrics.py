"""
DORA Metrics Service — Release Behavior Analysis
==================================================
Computes 4 DORA metrics from deploy_events:
  1. Deployment Frequency (deploys/day)
  2. Change Failure Rate (failed/total %)
  3. MTTR — Mean Time to Restore (avg duration of failure→success)
  4. Lead Time (commit→deploy, approximated from deploy event timestamps)

Correlation Layer:
  Cross-references DORA metrics with channel health to find:
  "deploy artti → drift azaldi mi?" etc.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger("controlplane.dora_metrics")


async def compute_dora_metrics(
    days: int = 30,
    environment: str | None = None,
) -> dict[str, Any]:
    """Compute raw DORA metrics from deploy_events collection."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    query: dict[str, Any] = {"started_at": {"$gte": cutoff}}
    if environment:
        query["environment"] = environment

    deploys = await db.deploy_events.find(query, {"_id": 0}).sort("started_at", 1).to_list(5000)

    if not deploys:
        return _empty_dora(days, environment)

    total = len(deploys)
    successes = [d for d in deploys if d.get("status") == "success"]
    failures = [d for d in deploys if d.get("status") != "success"]
    rollbacks = [d for d in deploys if d.get("rollback_of") or d.get("rollback")]

    # 1. Deployment Frequency
    first_deploy = deploys[0].get("started_at", cutoff)
    last_deploy = deploys[-1].get("started_at", datetime.now(UTC).isoformat())
    try:
        span_days = max(1, (datetime.fromisoformat(last_deploy) - datetime.fromisoformat(first_deploy)).days)
    except (ValueError, TypeError):
        span_days = max(1, days)

    deployment_frequency = round(total / span_days, 2)

    # 2. Change Failure Rate
    change_failure_rate = round((len(failures) / total) * 100, 1) if total > 0 else 0

    # 3. MTTR — time between failure and next success
    mttr_values: list[float] = []
    sorted_deploys = sorted(deploys, key=lambda d: d.get("started_at", ""))
    last_failure_time = None
    for d in sorted_deploys:
        if d.get("status") != "success" and last_failure_time is None:
            last_failure_time = d.get("started_at")
        elif d.get("status") == "success" and last_failure_time is not None:
            try:
                fail_dt = datetime.fromisoformat(last_failure_time)
                success_dt = datetime.fromisoformat(d.get("started_at", ""))
                mttr_minutes = (success_dt - fail_dt).total_seconds() / 60
                if 0 < mttr_minutes < 10080:  # < 7 days
                    mttr_values.append(mttr_minutes)
            except (ValueError, TypeError):
                pass
            last_failure_time = None

    mttr_avg_minutes = round(sum(mttr_values) / len(mttr_values), 1) if mttr_values else 0

    # 4. Lead Time (approximate: duration_seconds from deploy events)
    lead_times: list[float] = []
    for d in successes:
        dur = d.get("duration_seconds")
        if dur and isinstance(dur, (int, float)) and dur > 0:
            lead_times.append(dur / 60)  # convert to minutes

    lead_time_avg_minutes = round(sum(lead_times) / len(lead_times), 1) if lead_times else 0

    # Daily breakdown for trend
    daily: dict[str, dict[str, int]] = {}
    for d in deploys:
        day = d.get("started_at", "")[:10]
        if day not in daily:
            daily[day] = {"total": 0, "success": 0, "failure": 0, "rollback": 0}
        daily[day]["total"] += 1
        if d.get("status") == "success":
            daily[day]["success"] += 1
        else:
            daily[day]["failure"] += 1
        if d.get("rollback_of") or d.get("rollback"):
            daily[day]["rollback"] += 1

    trend = [{"date": k, **v} for k, v in sorted(daily.items())]

    return {
        "period_days": days,
        "environment": environment or "all",
        "total_deploys": total,
        "successful_deploys": len(successes),
        "failed_deploys": len(failures),
        "rollback_count": len(rollbacks),
        "metrics": {
            "deployment_frequency": {
                "value": deployment_frequency,
                "unit": "deploys/day",
                "rating": _rate_frequency(deployment_frequency),
            },
            "change_failure_rate": {
                "value": change_failure_rate,
                "unit": "%",
                "rating": _rate_cfr(change_failure_rate),
            },
            "mttr": {
                "value": mttr_avg_minutes,
                "unit": "minutes",
                "incidents": len(mttr_values),
                "rating": _rate_mttr(mttr_avg_minutes),
            },
            "lead_time": {
                "value": lead_time_avg_minutes,
                "unit": "minutes",
                "samples": len(lead_times),
                "rating": _rate_lead_time(lead_time_avg_minutes),
            },
        },
        "trend": trend,
        "computed_at": datetime.now(UTC).isoformat(),
    }


async def compute_dora_channel_correlation(
    days: int = 30,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Correlation layer: cross-reference DORA with channel health.

    Answers:
      - deploy artti → drift azaldi mi?
      - MTTR dustu → sync success artti mi?
      - change failure rate → import failure rate?
    """
    # Auto-detect tenant
    if not tenant_id:
        tenant = await db.organizations.find_one({}, {"_id": 0, "id": 1})
        if not tenant:
            room = await db.rooms.find_one({}, {"_id": 0, "tenant_id": 1})
            tenant_id = room.get("tenant_id") if room else None
        else:
            tenant_id = tenant.get("id")

    # Split period into two halves for comparison
    mid_days = days // 2
    now = datetime.now(UTC)
    mid_point = (now - timedelta(days=mid_days)).isoformat()
    start_point = (now - timedelta(days=days)).isoformat()
    now_iso = now.isoformat()

    # DORA: first half vs second half
    dora_first = await _count_deploys(start_point, mid_point)
    dora_second = await _count_deploys(mid_point, now_iso)

    # Channel health: drift events
    drift_first = await _count_timeline_events(
        tenant_id,
        "inventory_alignment",
        start_point,
        mid_point,
    )
    drift_second = await _count_timeline_events(
        tenant_id,
        "inventory_alignment",
        mid_point,
        now_iso,
    )

    # Sync events
    sync_first = await _count_sync_results(tenant_id, start_point, mid_point)
    sync_second = await _count_sync_results(tenant_id, mid_point, now_iso)

    # Import failures
    import_first = await _count_import_failures(tenant_id, start_point, mid_point)
    import_second = await _count_import_failures(tenant_id, mid_point, now_iso)

    correlations = []

    # Correlation 1: Deploy frequency vs drift
    if dora_first["total"] > 0 or dora_second["total"] > 0:
        freq_delta = dora_second["total"] - dora_first["total"]
        drift_delta = drift_second - drift_first
        correlations.append(
            {
                "name": "deploy_frequency_vs_drift",
                "question": "Deploy artti → drift azaldi mi?",
                "first_half": {"deploys": dora_first["total"], "drift_events": drift_first},
                "second_half": {"deploys": dora_second["total"], "drift_events": drift_second},
                "deploy_change": freq_delta,
                "drift_change": drift_delta,
                "inference": _infer_correlation(freq_delta, -drift_delta),
            }
        )

    # Correlation 2: Failure rate vs sync success
    cfr_first = round((dora_first["failed"] / max(1, dora_first["total"])) * 100, 1)
    cfr_second = round((dora_second["failed"] / max(1, dora_second["total"])) * 100, 1)
    correlations.append(
        {
            "name": "failure_rate_vs_sync",
            "question": "Change failure rate dustu → sync success artti mi?",
            "first_half": {
                "change_failure_rate": cfr_first,
                "sync_success": sync_first.get("success", 0),
                "sync_total": sync_first.get("total", 0),
            },
            "second_half": {
                "change_failure_rate": cfr_second,
                "sync_success": sync_second.get("success", 0),
                "sync_total": sync_second.get("total", 0),
            },
            "cfr_change": round(cfr_second - cfr_first, 1),
            "sync_success_change": sync_second.get("success", 0) - sync_first.get("success", 0),
            "inference": _infer_correlation(
                -(cfr_second - cfr_first),
                sync_second.get("success", 0) - sync_first.get("success", 0),
            ),
        }
    )

    # Correlation 3: MTTR vs import failures
    correlations.append(
        {
            "name": "mttr_vs_import_failures",
            "question": "MTTR iyilesti → import failure azaldi mi?",
            "first_half": {"import_failures": import_first},
            "second_half": {"import_failures": import_second},
            "import_failure_change": import_second - import_first,
            "inference": "improving" if import_second < import_first else ("stable" if import_second == import_first else "degrading"),
        }
    )

    return {
        "period_days": days,
        "tenant_id": tenant_id,
        "correlations": correlations,
        "computed_at": now_iso,
    }


# ── Helpers ──────────────────────────────────────────────────────────


async def _count_deploys(start: str, end: str) -> dict[str, int]:
    pipeline = [
        {"$match": {"started_at": {"$gte": start, "$lte": end}}},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "success": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$ne": ["$status", "success"]}, 1, 0]}},
            }
        },
    ]
    results = await db.deploy_events.aggregate(pipeline).to_list(1)
    if results:
        return {"total": results[0]["total"], "success": results[0]["success"], "failed": results[0]["failed"]}
    return {"total": 0, "success": 0, "failed": 0}


async def _count_timeline_events(
    tenant_id: str | None,
    entity_type: str,
    start: str,
    end: str,
) -> int:
    query: dict[str, Any] = {
        "entity_type": entity_type,
        "timestamp": {"$gte": start, "$lte": end},
    }
    if tenant_id:
        query["tenant_id"] = tenant_id
    return await db.event_timeline.count_documents(query)


async def _count_sync_results(
    tenant_id: str | None,
    start: str,
    end: str,
) -> dict[str, int]:
    query: dict[str, Any] = {"created_at": {"$gte": start, "$lte": end}}
    if tenant_id:
        query["tenant_id"] = tenant_id

    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "success": {"$sum": {"$cond": [{"$eq": ["$status", "succeeded"]}, 1, 0]}},
            }
        },
    ]
    results = await db.cm_sync_jobs.aggregate(pipeline).to_list(1)
    if results:
        return {"total": results[0]["total"], "success": results[0]["success"]}
    return {"total": 0, "success": 0}


async def _count_import_failures(
    tenant_id: str | None,
    start: str,
    end: str,
) -> int:
    query: dict[str, Any] = {
        "status": {"$in": ["failed", "error"]},
        "created_at": {"$gte": start, "$lte": end},
    }
    if tenant_id:
        query["tenant_id"] = tenant_id
    return await db.cm_reservation_imports.count_documents(query)


def _rate_frequency(freq: float) -> str:
    if freq >= 1.0:
        return "elite"
    elif freq >= 0.14:  # ~weekly
        return "high"
    elif freq >= 0.03:  # ~monthly
        return "medium"
    return "low"


def _rate_cfr(rate: float) -> str:
    if rate <= 5:
        return "elite"
    elif rate <= 15:
        return "high"
    elif rate <= 30:
        return "medium"
    return "low"


def _rate_mttr(minutes: float) -> str:
    if minutes == 0:
        return "no_data"
    if minutes < 60:
        return "elite"
    elif minutes < 1440:  # 1 day
        return "high"
    elif minutes < 10080:  # 1 week
        return "medium"
    return "low"


def _rate_lead_time(minutes: float) -> str:
    if minutes == 0:
        return "no_data"
    if minutes < 60:
        return "elite"
    elif minutes < 1440:
        return "high"
    elif minutes < 10080:
        return "medium"
    return "low"


def _infer_correlation(metric_a_delta: float, metric_b_delta: float) -> str:
    """Simple correlation inference between two deltas."""
    if metric_a_delta > 0 and metric_b_delta > 0:
        return "positive_correlation"
    elif metric_a_delta > 0 and metric_b_delta < 0:
        return "inverse_correlation"
    elif metric_a_delta == 0 or metric_b_delta == 0:
        return "insufficient_data"
    elif metric_a_delta < 0 and metric_b_delta < 0:
        return "co_declining"
    return "no_correlation"


def _empty_dora(days: int, environment: str | None) -> dict[str, Any]:
    return {
        "period_days": days,
        "environment": environment or "all",
        "total_deploys": 0,
        "successful_deploys": 0,
        "failed_deploys": 0,
        "rollback_count": 0,
        "metrics": {
            "deployment_frequency": {"value": 0, "unit": "deploys/day", "rating": "no_data"},
            "change_failure_rate": {"value": 0, "unit": "%", "rating": "no_data"},
            "mttr": {"value": 0, "unit": "minutes", "incidents": 0, "rating": "no_data"},
            "lead_time": {"value": 0, "unit": "minutes", "samples": 0, "rating": "no_data"},
        },
        "trend": [],
        "computed_at": datetime.now(UTC).isoformat(),
    }
