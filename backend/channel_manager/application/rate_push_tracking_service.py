"""
Rate Push Success Tracking Service.

Tracks rate push success/failure/retry metrics and integrates them into
the connector health score calculation.

Metrics:
  - rate_push_success_rate
  - rate_push_failure_rate
  - rate_push_retry_count
  - rate_push_avg_latency_ms
  - rate_push_last_success
  - rate_push_last_failure

Response parsing + failure classification:
  - provider_rejected: Provider returned error for rate data
  - validation_error: Rate data failed local validation
  - timeout: Request timed out
  - rate_limited: Provider rate limit hit
  - auth_error: Authentication failure
  - unknown: Unclassified error
"""

import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.rate_push_tracking")

RATE_PUSH_METRICS = "cm_rate_push_metrics"
_NO_ID = {"_id": 0}


class RatePushTrackingService:
    """Tracks and aggregates rate push operation metrics."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def record_rate_push(
        self,
        tenant_id: str,
        connector_id: str,
        success: bool,
        latency_ms: int = 0,
        error_type: str = "",
        error_message: str = "",
        update_count: int = 0,
        retry_count: int = 0,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Record a single rate push operation result."""
        now = datetime.now(UTC).isoformat()
        failure_class = self._classify_failure(error_type, error_message) if not success else ""

        record = {
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "success": success,
            "latency_ms": latency_ms,
            "error_type": error_type,
            "error_message": error_message[:500] if error_message else "",
            "failure_classification": failure_class,
            "update_count": update_count,
            "retry_count": retry_count,
            "correlation_id": correlation_id,
            "recorded_at": now,
        }
        await db[RATE_PUSH_METRICS].insert_one(record)
        return {"recorded": True, "failure_classification": failure_class}

    async def get_metrics(
        self,
        tenant_id: str,
        connector_id: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """Get aggregated rate push metrics for a connector."""
        datetime.now(UTC).isoformat()[:10]  # today
        query = {"tenant_id": tenant_id, "connector_id": connector_id}

        total = await db[RATE_PUSH_METRICS].count_documents(query)
        success_count = await db[RATE_PUSH_METRICS].count_documents({**query, "success": True})
        failure_count = total - success_count

        success_rate = round(success_count / max(total, 1) * 100, 1)
        failure_rate = round(failure_count / max(total, 1) * 100, 1)

        # Retry count
        pipeline = [
            {"$match": query},
            {"$group": {"_id": None, "total_retries": {"$sum": "$retry_count"}}},
        ]
        retry_result = await db[RATE_PUSH_METRICS].aggregate(pipeline).to_list(1)
        total_retries = retry_result[0]["total_retries"] if retry_result else 0

        # Average latency
        latency_pipeline = [
            {"$match": {**query, "success": True}},
            {"$group": {"_id": None, "avg_latency": {"$avg": "$latency_ms"}}},
        ]
        latency_result = await db[RATE_PUSH_METRICS].aggregate(latency_pipeline).to_list(1)
        avg_latency = round(latency_result[0]["avg_latency"], 0) if latency_result else 0

        # Failure breakdown
        failure_pipeline = [
            {"$match": {**query, "success": False}},
            {"$group": {"_id": "$failure_classification", "count": {"$sum": 1}}},
        ]
        failure_breakdown = {}
        async for doc in db[RATE_PUSH_METRICS].aggregate(failure_pipeline):
            failure_breakdown[doc["_id"] or "unknown"] = doc["count"]

        # Last success/failure
        last_success = await db[RATE_PUSH_METRICS].find_one({**query, "success": True}, _NO_ID, sort=[("recorded_at", -1)])
        last_failure = await db[RATE_PUSH_METRICS].find_one({**query, "success": False}, _NO_ID, sort=[("recorded_at", -1)])

        return {
            "connector_id": connector_id,
            "total_pushes": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "rate_push_success_rate": success_rate,
            "rate_push_failure_rate": failure_rate,
            "rate_push_retry_count": total_retries,
            "avg_latency_ms": avg_latency,
            "failure_breakdown": failure_breakdown,
            "last_success_at": last_success.get("recorded_at") if last_success else None,
            "last_failure_at": last_failure.get("recorded_at") if last_failure else None,
            "last_failure_reason": last_failure.get("error_message", "")[:200] if last_failure else None,
        }

    async def get_health_score_component(
        self,
        tenant_id: str,
        connector_id: str,
    ) -> float:
        """Return a health score component (0-100) based on rate push metrics."""
        metrics = await self.get_metrics(tenant_id, connector_id)
        success_rate = metrics.get("rate_push_success_rate", 100.0)
        return success_rate

    @staticmethod
    def _classify_failure(error_type: str, error_message: str) -> str:
        """Classify rate push failure into categories."""
        et = error_type.lower()
        em = error_message.lower()

        if "auth" in et or "401" in em:
            return "auth_error"
        if "ratelimit" in et or "429" in em or "rate limit" in em:
            return "rate_limited"
        if "timeout" in et or "timed out" in em:
            return "timeout"
        if "validation" in et or "invalid" in em or "schema" in em:
            return "validation_error"
        if "unavailable" in et or "500" in em or "502" in em or "503" in em:
            return "provider_unavailable"
        if error_type or error_message:
            return "provider_rejected"
        return "unknown"
