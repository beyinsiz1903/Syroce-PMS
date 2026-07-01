"""
HotelRunner v2 — Write Readiness Score
========================================

Calculates a composite 0–100 score representing
how ready the connector is to transition from
Shadow Mode to Live Write.

Score components (weighted):
  - Drift score     (25%) — fewer drifts = higher
  - Error rate      (25%) — lower error rate = higher
  - Retry health    (15%) — fewer retries = higher
  - DLQ cleanliness (15%) — empty DLQ = higher
  - Latency         (20%) — lower latency = higher
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger("hrv2.readiness")

COLL_METRICS = "connector_metrics"
COLL_DLQ = "connector_dlq"
COLL_RECON_DRIFTS = "connector_reconciliation_drifts"


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _score_inverse(value: float, good_threshold: float, bad_threshold: float) -> float:
    """
    Score inversely proportional to value.
    value <= good_threshold → 100
    value >= bad_threshold → 0
    Linear interpolation between.
    """
    if value <= good_threshold:
        return 100.0
    if value >= bad_threshold:
        return 0.0
    return _clamp(100.0 * (1.0 - (value - good_threshold) / (bad_threshold - good_threshold)))


async def calculate_readiness_score(tenant_id: str, hours: int = 24) -> dict[str, Any]:
    """
    Calculate the Write Readiness Score (0–100).

    Returns breakdown per component + overall score.
    """
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    # ── Gather raw data ──

    # 1. Overall metrics
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "provider": "hotelrunner_v2", "recorded_at": {"$gte": since}}},
        {
            "$group": {
                "_id": None,
                "total_ops": {"$sum": 1},
                "success_count": {"$sum": {"$cond": ["$success", 1, 0]}},
                "fail_count": {"$sum": {"$cond": ["$success", 0, 1]}},
                "avg_latency": {"$avg": "$duration_ms"},
            }
        },
    ]
    agg = await db[COLL_METRICS].aggregate(pipeline).to_list(1)
    m = agg[0] if agg else {"total_ops": 0, "success_count": 0, "fail_count": 0, "avg_latency": 0}

    total_ops = m["total_ops"]
    error_rate = (m["fail_count"] / total_ops * 100) if total_ops > 0 else 0.0
    avg_latency = m["avg_latency"] or 0
    retry_count = m["fail_count"]

    # 2. Drift count (24h)
    drift_count = await db[COLL_RECON_DRIFTS].count_documents(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner_v2",
            "created_at": {"$gte": since},
        }
    )

    # 3. DLQ count
    dlq_count = await db[COLL_DLQ].count_documents(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner",
        }
    )

    # ── Score components ──

    # Drift: 0 drifts = 100, >= 15 drifts = 0
    drift_score = _score_inverse(drift_count, good_threshold=0, bad_threshold=15)

    # Error rate: 0% = 100, >= 15% = 0
    error_score = _score_inverse(error_rate, good_threshold=0, bad_threshold=15)

    # Retry: 0 retries = 100, >= 30 = 0
    retry_score = _score_inverse(retry_count, good_threshold=0, bad_threshold=30)

    # DLQ: 0 entries = 100, >= 5 = 0
    dlq_score = _score_inverse(dlq_count, good_threshold=0, bad_threshold=5)

    # Latency: <= 1000ms = 100, >= 8000ms = 0
    latency_score = _score_inverse(avg_latency, good_threshold=1000, bad_threshold=8000)

    # ── Weighted total ──
    weights = {
        "drift": 0.25,
        "error_rate": 0.25,
        "retry": 0.15,
        "dlq": 0.15,
        "latency": 0.20,
    }

    overall = round(
        drift_score * weights["drift"] + error_score * weights["error_rate"] + retry_score * weights["retry"] + dlq_score * weights["dlq"] + latency_score * weights["latency"],
        1,
    )

    # Readiness verdict
    if overall >= 90:
        verdict = "ready"
        verdict_label = "Write icin hazir"
    elif overall >= 70:
        verdict = "caution"
        verdict_label = "Dikkatli ilerleyin"
    elif overall >= 50:
        verdict = "not_ready"
        verdict_label = "Henuz hazir degil"
    else:
        verdict = "blocked"
        verdict_label = "Engeller mevcut"

    # No-data case: if zero operations, mark as insufficient data
    if total_ops == 0:
        verdict = "no_data"
        verdict_label = "Yeterli veri yok"

    return {
        "tenant_id": tenant_id,
        "period_hours": hours,
        "calculated_at": datetime.now(UTC).isoformat(),
        "overall_score": overall,
        "verdict": verdict,
        "verdict_label": verdict_label,
        "components": {
            "drift": {
                "score": round(drift_score, 1),
                "weight": weights["drift"],
                "raw_value": drift_count,
                "unit": "drifts",
            },
            "error_rate": {
                "score": round(error_score, 1),
                "weight": weights["error_rate"],
                "raw_value": round(error_rate, 2),
                "unit": "%",
            },
            "retry": {
                "score": round(retry_score, 1),
                "weight": weights["retry"],
                "raw_value": retry_count,
                "unit": "retries",
            },
            "dlq": {
                "score": round(dlq_score, 1),
                "weight": weights["dlq"],
                "raw_value": dlq_count,
                "unit": "entries",
            },
            "latency": {
                "score": round(latency_score, 1),
                "weight": weights["latency"],
                "raw_value": round(avg_latency, 1),
                "unit": "ms",
            },
        },
        "raw_metrics": {
            "total_operations": total_ops,
            "error_rate_pct": round(error_rate, 2),
            "drift_count": drift_count,
            "dlq_count": dlq_count,
            "retry_count": retry_count,
            "avg_latency_ms": round(avg_latency, 1),
        },
    }
