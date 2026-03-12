"""
Connector Health Trend Analytics Service.

Stores and retrieves time-series health data for trend analysis.

Metrics tracked over time:
  - daily_health_score
  - weekly_health_score
  - sync_success_rate_trend
  - import_success_rate_trend
  - alert_frequency_trend
  - retry_frequency_trend

Enables SLA tracking and early detection of degradation patterns.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from core.database import db
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.health_trend")

HEALTH_SNAPSHOTS = "cm_health_snapshots"
_NO_ID = {"_id": 0}


class HealthTrendService:
    """Manages health trend snapshots and provides trend analytics."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    async def record_health_snapshot(
        self,
        tenant_id: str,
        connector_id: str,
        health_score: float,
        sync_success_rate: float,
        import_success_rate: float,
        active_alerts: int,
        retry_count: int,
        rate_push_success_rate: float = 100.0,
    ) -> Dict[str, Any]:
        """Record a health snapshot for trend tracking."""
        now = datetime.now(timezone.utc)
        snapshot = {
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "health_score": health_score,
            "sync_success_rate": sync_success_rate,
            "import_success_rate": import_success_rate,
            "rate_push_success_rate": rate_push_success_rate,
            "active_alerts": active_alerts,
            "retry_count": retry_count,
            "date": now.strftime("%Y-%m-%d"),
            "hour": now.hour,
            "recorded_at": now.isoformat(),
        }
        await db[HEALTH_SNAPSHOTS].insert_one(snapshot)
        return {"recorded": True, "date": snapshot["date"]}

    async def get_daily_trend(
        self, tenant_id: str, connector_id: str, days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get daily health score trend for a connector."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        pipeline = [
            {"$match": {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "date": {"$gte": cutoff},
            }},
            {"$group": {
                "_id": "$date",
                "avg_health_score": {"$avg": "$health_score"},
                "avg_sync_rate": {"$avg": "$sync_success_rate"},
                "avg_import_rate": {"$avg": "$import_success_rate"},
                "avg_rate_push_rate": {"$avg": "$rate_push_success_rate"},
                "total_alerts": {"$sum": "$active_alerts"},
                "total_retries": {"$sum": "$retry_count"},
                "snapshot_count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
            {"$project": {
                "_id": 0,
                "date": "$_id",
                "health_score": {"$round": ["$avg_health_score", 1]},
                "sync_success_rate": {"$round": ["$avg_sync_rate", 1]},
                "import_success_rate": {"$round": ["$avg_import_rate", 1]},
                "rate_push_success_rate": {"$round": ["$avg_rate_push_rate", 1]},
                "alert_count": "$total_alerts",
                "retry_count": "$total_retries",
                "snapshot_count": 1,
            }},
        ]
        return await db[HEALTH_SNAPSHOTS].aggregate(pipeline).to_list(days + 1)

    async def get_weekly_trend(
        self, tenant_id: str, connector_id: str, weeks: int = 12,
    ) -> List[Dict[str, Any]]:
        """Get weekly aggregated health trend."""
        cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        pipeline = [
            {"$match": {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "date": {"$gte": cutoff},
            }},
            {"$addFields": {
                "date_obj": {"$dateFromString": {"dateString": "$date", "format": "%Y-%m-%d"}},
            }},
            {"$group": {
                "_id": {"$isoWeek": "$date_obj"},
                "week_start": {"$min": "$date"},
                "week_end": {"$max": "$date"},
                "avg_health_score": {"$avg": "$health_score"},
                "avg_sync_rate": {"$avg": "$sync_success_rate"},
                "avg_import_rate": {"$avg": "$import_success_rate"},
                "total_alerts": {"$sum": "$active_alerts"},
                "total_retries": {"$sum": "$retry_count"},
            }},
            {"$sort": {"week_start": 1}},
            {"$project": {
                "_id": 0,
                "week_number": "$_id",
                "week_start": 1,
                "week_end": 1,
                "health_score": {"$round": ["$avg_health_score", 1]},
                "sync_success_rate": {"$round": ["$avg_sync_rate", 1]},
                "import_success_rate": {"$round": ["$avg_import_rate", 1]},
                "alert_count": "$total_alerts",
                "retry_count": "$total_retries",
            }},
        ]
        return await db[HEALTH_SNAPSHOTS].aggregate(pipeline).to_list(weeks + 1)

    async def get_trend_summary(
        self, tenant_id: str, connector_id: str,
    ) -> Dict[str, Any]:
        """Get trend summary comparing recent vs previous period."""
        now = datetime.now(timezone.utc)
        recent_cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        previous_cutoff = (now - timedelta(days=14)).strftime("%Y-%m-%d")

        base_q = {"tenant_id": tenant_id, "connector_id": connector_id}

        recent = await self._period_avg(base_q, recent_cutoff, now.strftime("%Y-%m-%d"))
        previous = await self._period_avg(base_q, previous_cutoff, recent_cutoff)

        def _delta(curr: float, prev: float) -> float:
            if prev == 0:
                return 0.0
            return round(curr - prev, 1)

        return {
            "connector_id": connector_id,
            "recent_period": {"from": recent_cutoff, "to": now.strftime("%Y-%m-%d")},
            "previous_period": {"from": previous_cutoff, "to": recent_cutoff},
            "health_score": {
                "current": recent.get("health_score", 0),
                "previous": previous.get("health_score", 0),
                "delta": _delta(recent.get("health_score", 0), previous.get("health_score", 0)),
                "trend": "up" if recent.get("health_score", 0) > previous.get("health_score", 0) else "down" if recent.get("health_score", 0) < previous.get("health_score", 0) else "stable",
            },
            "sync_success_rate": {
                "current": recent.get("sync_success_rate", 0),
                "previous": previous.get("sync_success_rate", 0),
                "delta": _delta(recent.get("sync_success_rate", 0), previous.get("sync_success_rate", 0)),
            },
            "import_success_rate": {
                "current": recent.get("import_success_rate", 0),
                "previous": previous.get("import_success_rate", 0),
                "delta": _delta(recent.get("import_success_rate", 0), previous.get("import_success_rate", 0)),
            },
            "alert_frequency": {
                "current": recent.get("alert_count", 0),
                "previous": previous.get("alert_count", 0),
            },
            "retry_frequency": {
                "current": recent.get("retry_count", 0),
                "previous": previous.get("retry_count", 0),
            },
        }

    async def _period_avg(self, base_q: Dict, from_date: str, to_date: str) -> Dict[str, Any]:
        """Get average metrics for a period."""
        pipeline = [
            {"$match": {**base_q, "date": {"$gte": from_date, "$lt": to_date}}},
            {"$group": {
                "_id": None,
                "health_score": {"$avg": "$health_score"},
                "sync_success_rate": {"$avg": "$sync_success_rate"},
                "import_success_rate": {"$avg": "$import_success_rate"},
                "alert_count": {"$sum": "$active_alerts"},
                "retry_count": {"$sum": "$retry_count"},
            }},
        ]
        result = await db[HEALTH_SNAPSHOTS].aggregate(pipeline).to_list(1)
        if result:
            r = result[0]
            return {
                "health_score": round(r.get("health_score", 0) or 0, 1),
                "sync_success_rate": round(r.get("sync_success_rate", 0) or 0, 1),
                "import_success_rate": round(r.get("import_success_rate", 0) or 0, 1),
                "alert_count": r.get("alert_count", 0),
                "retry_count": r.get("retry_count", 0),
            }
        return {"health_score": 0, "sync_success_rate": 0, "import_success_rate": 0, "alert_count": 0, "retry_count": 0}
