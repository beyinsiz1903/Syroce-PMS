"""
MongoDB Production Validator — Connection pool monitoring, replica set detection,
slow query metrics, index validation, schema drift detection, and collection health.
"""
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("infra.mongo_production")


# Collections that must exist with indexes
CRITICAL_COLLECTIONS = [
    "users", "tenants", "bookings", "rooms", "guests", "folios",
    "invoices", "payments", "companies", "rates", "channel_connections",
    "audit_logs", "loyalty_programs", "loyalty_transactions",
]

SECONDARY_COLLECTIONS = [
    "event_bus_log", "messaging_delivery_logs", "observability_traces",
    "alert_history", "pipeline_runs", "analytics_export_history",
    "notification_queue", "housekeeping_tasks", "maintenance_work_orders",
]

EXPECTED_INDEXES = {
    "users": ["email_1", "tenant_id_1"],
    "bookings": ["tenant_id_1", "status_1", "check_in_1"],
    "rooms": ["tenant_id_1", "room_number_1"],
    "guests": ["tenant_id_1", "email_1"],
    "folios": ["tenant_id_1", "booking_id_1"],
    "audit_logs": ["tenant_id_1", "created_at_-1"],
}


class MongoProductionValidator:
    """Validates MongoDB production readiness."""

    def __init__(self):
        self._db = None
        self._client = None

    def set_db(self, db, client=None):
        """Set database reference from server startup."""
        self._db = db
        self._client = client

    async def get_connection_pool_info(self) -> dict[str, Any]:
        """Get connection pool statistics."""
        if self._db is None:
            return {"status": "not_connected", "error": "Database not initialized"}

        try:
            server_status = await self._db.command("serverStatus")
            connections = server_status.get("connections", {})
            return {
                "status": "connected",
                "current_connections": connections.get("current", 0),
                "available_connections": connections.get("available", 0),
                "total_created": connections.get("totalCreated", 0),
                "active": connections.get("active", 0),
                "mongo_version": server_status.get("version", "unknown"),
                "uptime_seconds": server_status.get("uptimeMillis", 0) / 1000,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def detect_replica_set(self) -> dict[str, Any]:
        """Detect if connected to a replica set and its health."""
        if self._db is None:
            return {"status": "not_connected", "is_replica_set": False}

        try:
            rs_status = await self._db.command("replSetGetStatus")
            members = []
            for m in rs_status.get("members", []):
                members.append({
                    "name": m.get("name"),
                    "state_str": m.get("stateStr"),
                    "health": m.get("health"),
                    "uptime": m.get("uptime", 0),
                    "optime_date": str(m.get("optimeDate", "")),
                })
            return {
                "is_replica_set": True,
                "set_name": rs_status.get("set", "unknown"),
                "my_state": rs_status.get("myState", 0),
                "members": members,
                "status": "healthy" if all(m["health"] == 1 for m in members) else "degraded",
            }
        except Exception:
            return {"is_replica_set": False, "status": "standalone", "note": "Not a replica set member"}

    async def get_slow_query_metrics(self, threshold_ms: int = 100) -> dict[str, Any]:
        """Get slow query statistics from profiling data."""
        if self._db is None:
            return {"status": "not_connected"}

        try:
            profile_level = await self._db.command("profile", -1)
            current_level = profile_level.get("was", 0)

            slow_queries = []
            if current_level > 0:
                cursor = self._db["system.profile"].find(
                    {"millis": {"$gte": threshold_ms}}
                ).sort("millis", -1).limit(20)
                async for doc in cursor:
                    slow_queries.append({
                        "operation": doc.get("op", "unknown"),
                        "namespace": doc.get("ns", "unknown"),
                        "millis": doc.get("millis", 0),
                        "timestamp": str(doc.get("ts", "")),
                        "query_shape": str(doc.get("command", {}))[:200],
                    })

            return {
                "profiling_level": current_level,
                "threshold_ms": threshold_ms,
                "slow_query_count": len(slow_queries),
                "slow_queries": slow_queries,
                "status": "monitoring" if current_level > 0 else "profiling_disabled",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def validate_indexes(self) -> dict[str, Any]:
        """Validate expected indexes exist on critical collections."""
        if self._db is None:
            return {"status": "not_connected"}

        results = {}
        missing_indexes = []
        for collection, expected in EXPECTED_INDEXES.items():
            try:
                existing = await self._db[collection].index_information()
                existing_names = set(existing.keys())
                missing = [idx for idx in expected if idx not in existing_names]
                results[collection] = {
                    "expected": expected,
                    "existing": list(existing_names - {"_id_"}),
                    "missing": missing,
                    "status": "complete" if not missing else "incomplete",
                }
                if missing:
                    missing_indexes.extend([f"{collection}.{idx}" for idx in missing])
            except Exception as e:
                results[collection] = {"status": "error", "error": str(e)}

        return {
            "validated_at": datetime.now(UTC).isoformat(),
            "collections_checked": len(results),
            "missing_index_count": len(missing_indexes),
            "missing_indexes": missing_indexes,
            "details": results,
            "status": "valid" if not missing_indexes else "action_required",
        }

    async def detect_schema_drift(self) -> dict[str, Any]:
        """Detect potential schema drift by sampling document structures."""
        if self._db is None:
            return {"status": "not_connected"}

        drift_report = {}
        for coll_name in CRITICAL_COLLECTIONS[:8]:
            try:
                sample = await self._db[coll_name].find_one(
                    {}, {"_id": 0}
                )
                if sample:
                    drift_report[coll_name] = {
                        "field_count": len(sample.keys()),
                        "fields": sorted(sample.keys()),
                        "status": "sampled",
                    }
                else:
                    drift_report[coll_name] = {"status": "empty"}
            except Exception as e:
                drift_report[coll_name] = {"status": "error", "error": str(e)}

        return {
            "scanned_at": datetime.now(UTC).isoformat(),
            "collections_scanned": len(drift_report),
            "details": drift_report,
        }

    async def get_collection_health(self) -> dict[str, Any]:
        """Get health summary for all known collections."""
        if self._db is None:
            return {"status": "not_connected"}

        all_collections = CRITICAL_COLLECTIONS + SECONDARY_COLLECTIONS
        health = {"critical": {}, "secondary": {}}
        total_docs = 0

        for coll_name in all_collections:
            category = "critical" if coll_name in CRITICAL_COLLECTIONS else "secondary"
            try:
                count = await self._db[coll_name].estimated_document_count()
                stats = {"document_count": count, "status": "active" if count > 0 else "empty"}
                total_docs += count
            except Exception:
                stats = {"document_count": 0, "status": "missing"}
            health[category][coll_name] = stats

        return {
            "checked_at": datetime.now(UTC).isoformat(),
            "total_documents": total_docs,
            "critical_collections": len(CRITICAL_COLLECTIONS),
            "secondary_collections": len(SECONDARY_COLLECTIONS),
            "health": health,
        }

    async def get_full_report(self) -> dict[str, Any]:
        """Comprehensive MongoDB production report."""
        pool = await self.get_connection_pool_info()
        replica = await self.detect_replica_set()
        indexes = await self.validate_indexes()
        collections = await self.get_collection_health()

        statuses = [pool.get("status"), indexes.get("status")]
        if any(s == "error" for s in statuses):
            overall = "error"
        elif any(s in ("incomplete", "action_required") for s in statuses):
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "overall_status": overall,
            "connection_pool": pool,
            "replica_set": replica,
            "index_validation": indexes,
            "collection_health": collections,
        }


mongo_validator = MongoProductionValidator()
