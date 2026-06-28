"""
MongoDB Persistence Repositories for enterprise modules.
Migrates in-memory stores to MongoDB with TTL, retention, and tenant isolation.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger("persistence.repositories")


class EventReplayRepository:
    """MongoDB-backed event replay with TTL and retention."""

    COLLECTION = "event_bus_log"
    RETENTION_DAYS = 30

    async def ensure_indexes(self):
        coll = db[self.COLLECTION]
        await coll.create_index([("tenant_id", 1), ("sequence", 1)])
        await coll.create_index([("tenant_id", 1), ("timestamp", -1)])
        await coll.create_index([("tenant_id", 1), ("event_type", 1)])
        await coll.create_index([("timestamp", 1)], expireAfterSeconds=self.RETENTION_DAYS * 86400)

    async def get_backlog_size(self, tenant_id: str) -> int:
        one_day_ago = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        return await db[self.COLLECTION].count_documents({"tenant_id": tenant_id, "timestamp": {"$gte": one_day_ago}})


class MessagingDeliveryRepository:
    """MongoDB persistence for messaging delivery logs with retention."""

    COLLECTION = "messaging_delivery_logs"
    RETENTION_DAYS = 90

    async def ensure_indexes(self):
        coll = db[self.COLLECTION]
        await coll.create_index([("tenant_id", 1), ("created_at", -1)])
        await coll.create_index([("tenant_id", 1), ("status", 1)])
        await coll.create_index([("tenant_id", 1), ("channel", 1)])
        await coll.create_index([("id", 1)], unique=True)
        await coll.create_index([("status", 1), ("next_retry_at", 1)])

    async def get_retry_queue(self, tenant_id: str, limit: int = 50) -> list[dict]:
        now = datetime.now(UTC).isoformat()
        return (
            await db[self.COLLECTION]
            .find(
                {
                    "tenant_id": tenant_id,
                    "status": "failed",
                    "retry_count": {"$lt": 3},
                    "$or": [
                        {"next_retry_at": {"$lte": now}},
                        {"next_retry_at": None},
                    ],
                },
                {"_id": 0},
            )
            .sort("created_at", 1)
            .to_list(limit)
        )


class AnalyticsExportRepository:
    """MongoDB persistence for analytics export history."""

    COLLECTION = "analytics_export_history"
    RETENTION_DAYS = 365

    async def ensure_indexes(self):
        coll = db[self.COLLECTION]
        await coll.create_index([("tenant_id", 1), ("created_at", -1)])
        await coll.create_index([("id", 1)], unique=True)
        await coll.create_index([("status", 1)])

    async def save_export(self, tenant_id: str, export_type: str, format_type: str, file_path: str, status: str = "completed", metadata: dict = None) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "export_type": export_type,
            "format": format_type,
            "file_path": file_path,
            "status": status,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db[self.COLLECTION].insert_one(doc)
        return {k: v for k, v in doc.items() if k != "_id"}

    async def get_recent_exports(self, tenant_id: str, limit: int = 50) -> list[dict]:
        return await db[self.COLLECTION].find({"tenant_id": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(limit)


class ObservabilityTraceRepository:
    """MongoDB persistence for observability traces."""

    COLLECTION = "observability_traces"
    RETENTION_DAYS = 14

    async def ensure_indexes(self):
        coll = db[self.COLLECTION]
        await coll.create_index([("started_at", -1)])
        await coll.create_index([("tenant_id", 1), ("started_at", -1)])
        await coll.create_index([("is_slow", 1)])
        await coll.create_index([("request_path", 1)])
        await coll.create_index([("started_at", 1)], expireAfterSeconds=self.RETENTION_DAYS * 86400)


class ObservabilityMetricsRepository:
    """MongoDB persistence for observability metrics snapshots."""

    COLLECTION = "observability_metrics"
    RETENTION_DAYS = 30

    async def ensure_indexes(self):
        coll = db[self.COLLECTION]
        await coll.create_index([("timestamp", -1)])
        await coll.create_index([("timestamp", 1)], expireAfterSeconds=self.RETENTION_DAYS * 86400)


class ObservabilityErrorRepository:
    """MongoDB persistence for error tracking."""

    COLLECTION = "observability_errors"
    RETENTION_DAYS = 90

    async def ensure_indexes(self):
        coll = db[self.COLLECTION]
        await coll.create_index([("timestamp", -1)])
        await coll.create_index([("tenant_id", 1), ("timestamp", -1)])
        await coll.create_index([("severity", 1)])
        await coll.create_index([("module", 1)])
        await coll.create_index([("id", 1)], unique=True)


class AlertHistoryRepository:
    """MongoDB persistence for alert history."""

    COLLECTION = "alert_history"
    RETENTION_DAYS = 90

    async def ensure_indexes(self):
        coll = db[self.COLLECTION]
        await coll.create_index([("created_at", -1)])
        await coll.create_index([("alert_type", 1)])
        await coll.create_index([("severity", 1)])
        await coll.create_index([("acknowledged", 1)])

    async def save_alert(self, alert_type: str, severity: str, title: str, message: str, context: dict = None, runbook_hint: str = None) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "alert_type": alert_type,
            "severity": severity,
            "title": title,
            "message": message,
            "context": context or {},
            "runbook_hint": runbook_hint,
            "acknowledged": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db[self.COLLECTION].insert_one(doc)
        return {k: v for k, v in doc.items() if k != "_id"}

    async def get_recent_alerts(self, limit: int = 50, severity: str = None, unacknowledged_only: bool = False) -> list[dict]:
        q: dict[str, Any] = {}
        if severity:
            q["severity"] = severity
        if unacknowledged_only:
            q["acknowledged"] = False
        return await db[self.COLLECTION].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> dict:
        await db[self.COLLECTION].update_one(
            {"id": alert_id},
            {
                "$set": {
                    "acknowledged": True,
                    "acknowledged_by": user_id,
                    "acknowledged_at": datetime.now(UTC).isoformat(),
                }
            },
        )
        return {"id": alert_id, "acknowledged": True}


class PipelineRunRepository:
    """MongoDB persistence for data pipeline runs."""

    COLLECTION = "pipeline_runs"

    async def ensure_indexes(self):
        coll = db[self.COLLECTION]
        await coll.create_index([("started_at", -1)])
        await coll.create_index([("status", 1)])
        await coll.create_index([("pipeline_type", 1)])


# ── Global initialization ──


async def ensure_all_indexes():
    """Create all MongoDB indexes for persistence repositories."""
    repos = [
        EventReplayRepository(),
        MessagingDeliveryRepository(),
        AnalyticsExportRepository(),
        ObservabilityTraceRepository(),
        ObservabilityMetricsRepository(),
        ObservabilityErrorRepository(),
        AlertHistoryRepository(),
        PipelineRunRepository(),
    ]
    for repo in repos:
        try:
            await repo.ensure_indexes()
        except Exception as e:
            logger.warning(f"Index creation failed for {repo.__class__.__name__}: {e}")
    logger.info(f"MongoDB indexes ensured for {len(repos)} repositories")


# Singleton instances
event_replay_repo = EventReplayRepository()
messaging_delivery_repo = MessagingDeliveryRepository()
analytics_export_repo = AnalyticsExportRepository()
trace_repo = ObservabilityTraceRepository()
metrics_repo = ObservabilityMetricsRepository()
error_repo = ObservabilityErrorRepository()
alert_history_repo = AlertHistoryRepository()
pipeline_run_repo = PipelineRunRepository()
