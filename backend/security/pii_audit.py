"""
PII Access Audit — Logs every access to PII data with tenant context.

Provides:
  - Structured audit logging for PII field access
  - Unmask event tracking (who viewed what, when)
  - Anomaly detection for excessive PII access
  - MongoDB-backed persistent audit trail with TTL
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("security.pii_audit")

COLL_PII_AUDIT = "pii_access_audit"


class PIIAuditLogger:
    """Logs PII access events to MongoDB."""

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            from core.database import db

            self._db = db
        return self._db

    async def log_access(
        self,
        *,
        tenant_id: str,
        user_id: str = "",
        user_role: str = "",
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        pii_fields: list[str] | None = None,
        was_unmasked: bool = False,
        ip_address: str = "",
        endpoint: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a PII access event."""
        record = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "user_role": user_role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "pii_fields_accessed": pii_fields or [],
            "was_unmasked": was_unmasked,
            "ip_address": ip_address,
            "endpoint": endpoint,
            "metadata": metadata or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            db = self._get_db()
            await db[COLL_PII_AUDIT].insert_one(record)
        except Exception:
            logger.exception("Failed to write PII access audit")

    async def get_audit_trail(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        was_unmasked: bool | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> dict[str, Any]:
        """Query PII access audit trail."""
        query: dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if user_id:
            query["user_id"] = user_id
        if was_unmasked is not None:
            query["was_unmasked"] = was_unmasked

        db = self._get_db()
        coll = db[COLL_PII_AUDIT]
        total = await coll.count_documents(query)
        items = await coll.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "skip": skip,
        }

    async def get_anomalies(
        self,
        *,
        hours: int = 24,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Detect anomalous PII access patterns."""
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        db = self._get_db()
        coll = db[COLL_PII_AUDIT]

        # High-volume unmask requests
        pipeline = [
            {
                "$match": {
                    "was_unmasked": True,
                    "timestamp": {"$gte": cutoff},
                    **({"tenant_id": tenant_id} if tenant_id else {}),
                }
            },
            {
                "$group": {
                    "_id": {"user_id": "$user_id", "user_role": "$user_role"},
                    "unmask_count": {"$sum": 1},
                    "unique_resources": {"$addToSet": "$resource_id"},
                    "last_access": {"$max": "$timestamp"},
                }
            },
            {"$match": {"unmask_count": {"$gt": 10}}},
            {"$sort": {"unmask_count": -1}},
            {"$limit": 20},
        ]

        anomalies = []
        try:
            async for doc in coll.aggregate(pipeline):
                anomalies.append(
                    {
                        "user_id": doc["_id"]["user_id"],
                        "user_role": doc["_id"]["user_role"],
                        "unmask_count": doc["unmask_count"],
                        "unique_resources_accessed": len(doc["unique_resources"]),
                        "last_access": doc["last_access"],
                        "severity": "critical" if doc["unmask_count"] > 50 else "warning",
                    }
                )
        except Exception:
            logger.exception("PII anomaly detection failed")

        return {
            "anomalies": anomalies,
            "window_hours": hours,
            "threshold": 10,
        }

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient audit queries."""
        db = self._get_db()
        coll = db[COLL_PII_AUDIT]
        await coll.create_index([("tenant_id", 1), ("timestamp", -1)])
        await coll.create_index([("user_id", 1), ("timestamp", -1)])
        await coll.create_index([("was_unmasked", 1), ("timestamp", -1)])
        await coll.create_index("timestamp", expireAfterSeconds=180 * 86400)  # 180-day TTL


# Singleton
_pii_audit: PIIAuditLogger | None = None


def get_pii_audit() -> PIIAuditLogger:
    global _pii_audit
    if _pii_audit is None:
        _pii_audit = PIIAuditLogger()
    return _pii_audit
