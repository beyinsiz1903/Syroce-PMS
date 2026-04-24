"""
PMS / Night Audit — Service Layer
Orchestrates audit logs, error logs, night audit reports,
OTA sync logs, and maintenance prediction logs. No FastAPI dependencies.
"""
import logging
from datetime import UTC, datetime
from typing import Any

from bson import Binary, ObjectId
from bson.decimal128 import Decimal128

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


def _sanitize_bson(obj: Any) -> Any:
    """Recursively convert BSON ObjectId / datetime to JSON-safe primitives.
    Sprint 33: fixes 500 on `/api/audit-logs` when nested `details` field
    contained an ObjectId from legacy log entries.
    """
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, Decimal128):
        return float(obj.to_decimal())
    if isinstance(obj, Binary):
        return obj.hex()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _sanitize_bson(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_bson(v) for v in obj]
    return obj


class NightAuditService:
    """Business logic for night audit and log management."""

    def __init__(self):
        from core.database import db
        self._db = db

    # ------------------------------------------------------------------
    # Audit Logs
    # ------------------------------------------------------------------
    async def get_audit_logs(
        self, ctx: OperationContext,
        entity_type: str | None = None, entity_id: str | None = None,
        user_id: str | None = None, action: str | None = None,
        start_date: str | None = None, end_date: str | None = None,
        limit: int = 100,
    ) -> ServiceResult:
        if not getattr(ctx, "actor_is_super_admin", False) and ctx.actor_role not in ("super_admin", "admin"):
            return ServiceResult.fail("Insufficient permissions", "FORBIDDEN")

        query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if entity_type:
            query["entity_type"] = entity_type
        if entity_id:
            query["entity_id"] = entity_id
        if user_id:
            query["user_id"] = user_id
        if action:
            query["action"] = action
        if start_date and end_date:
            query["timestamp"] = {
                "$gte": datetime.fromisoformat(start_date).isoformat(),
                "$lte": datetime.fromisoformat(end_date).isoformat(),
            }

        logs = await self._db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
        sanitized = _sanitize_bson(logs)
        return ServiceResult.success({
            "logs": sanitized,
            "count": len(sanitized),
            "filters_applied": {k: v for k, v in query.items() if k != "tenant_id"},
        })

    # ------------------------------------------------------------------
    # Error Logs
    # ------------------------------------------------------------------
    async def get_error_logs(
        self, ctx: OperationContext,
        start_date: str | None = None, end_date: str | None = None,
        severity: str | None = None, endpoint: str | None = None,
        resolved: bool | None = None, limit: int = 100, skip: int = 0,
    ) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if start_date or end_date:
            date_filter: dict[str, str] = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            query["timestamp"] = date_filter
        if severity:
            query["severity"] = severity
        if endpoint:
            from security.query_safety import safe_search_term
            if (_s := safe_search_term(endpoint)):
                query["endpoint"] = {"$regex": _s, "$options": "i"}
        if resolved is not None:
            query["resolved"] = resolved

        logs = []
        async for log in self._db.error_logs.find(query).sort("timestamp", -1).skip(skip).limit(limit):
            log.pop("_id", None)
            logs.append(log)

        total_count = await self._db.error_logs.count_documents(query)
        severity_stats: dict[str, int] = {}
        async for doc in self._db.error_logs.aggregate([
            {"$match": {"tenant_id": ctx.tenant_id}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]):
            severity_stats[doc["_id"]] = doc["count"]

        return ServiceResult.success({
            "logs": logs, "total_count": total_count,
            "returned_count": len(logs), "skip": skip, "limit": limit,
            "severity_stats": severity_stats,
        })

    async def resolve_error_log(self, ctx: OperationContext, error_id: str, notes: str | None = None) -> ServiceResult:
        result = await self._db.error_logs.update_one(
            {"id": error_id, "tenant_id": ctx.tenant_id},
            {"$set": {"resolved": True, "resolved_at": datetime.now(UTC).isoformat(), "resolved_by": ctx.actor_id, "resolution_notes": notes}},
        )
        if result.modified_count == 0:
            return ServiceResult.fail("Error log not found", "NOT_FOUND")
        return ServiceResult.success({"success": True, "message": "Error log marked as resolved"})

    # ------------------------------------------------------------------
    # Night Audit Logs
    # ------------------------------------------------------------------
    async def get_night_audit_logs(
        self, ctx: OperationContext,
        start_date: str | None = None, end_date: str | None = None,
        status: str | None = None, limit: int = 100, skip: int = 0,
    ) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if start_date or end_date:
            date_filter: dict[str, str] = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            query["audit_date"] = date_filter
        if status:
            query["status"] = status

        logs = []
        async for log in self._db.night_audit_logs.find(query).sort("timestamp", -1).skip(skip).limit(limit):
            log.pop("_id", None)
            logs.append(log)

        total_count = await self._db.night_audit_logs.count_documents(query)
        stats = {"total_audits": total_count, "successful": 0, "failed": 0, "total_charges": 0.0, "total_rooms": 0}
        async for log in self._db.night_audit_logs.find({"tenant_id": ctx.tenant_id}):
            if log.get("status") == "completed":
                stats["successful"] += 1
            elif log.get("status") == "failed":
                stats["failed"] += 1
            stats["total_charges"] += log.get("total_amount", 0)
            stats["total_rooms"] += log.get("rooms_processed", 0)
        stats["success_rate"] = round(stats["successful"] / stats["total_audits"] * 100, 1) if stats["total_audits"] > 0 else 0

        return ServiceResult.success({
            "logs": logs, "total_count": total_count,
            "returned_count": len(logs), "skip": skip, "limit": limit,
            "stats": stats,
        })

    # ------------------------------------------------------------------
    # OTA Sync Logs
    # ------------------------------------------------------------------
    async def get_ota_sync_logs(
        self, ctx: OperationContext,
        start_date: str | None = None, end_date: str | None = None,
        channel: str | None = None, sync_type: str | None = None,
        status: str | None = None, limit: int = 100, skip: int = 0,
    ) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if start_date or end_date:
            df: dict[str, str] = {}
            if start_date:
                df["$gte"] = start_date
            if end_date:
                df["$lte"] = end_date
            query["timestamp"] = df
        if channel:
            query["channel"] = channel
        if sync_type:
            query["sync_type"] = sync_type
        if status:
            query["status"] = status

        logs = []
        async for log in self._db.ota_sync_logs.find(query).sort("timestamp", -1).skip(skip).limit(limit):
            log.pop("_id", None)
            logs.append(log)

        total_count = await self._db.ota_sync_logs.count_documents(query)
        channel_stats: dict[str, Any] = {}
        async for doc in self._db.ota_sync_logs.aggregate([
            {"$match": {"tenant_id": ctx.tenant_id}},
            {"$group": {
                "_id": "$channel",
                "total": {"$sum": 1},
                "successful": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                "records_synced": {"$sum": "$records_synced"},
            }},
        ]):
            name = doc["_id"]
            channel_stats[name] = {
                "total_syncs": doc["total"],
                "successful": doc["successful"],
                "failed": doc["failed"],
                "success_rate": round(doc["successful"] / doc["total"] * 100, 1) if doc["total"] > 0 else 0,
                "records_synced": doc["records_synced"],
            }

        return ServiceResult.success({
            "logs": logs, "total_count": total_count,
            "returned_count": len(logs), "skip": skip, "limit": limit,
            "channel_stats": channel_stats,
        })

    # ------------------------------------------------------------------
    # RMS Publish Logs
    # ------------------------------------------------------------------
    async def get_rms_publish_logs(
        self, ctx: OperationContext,
        start_date: str | None = None, end_date: str | None = None,
        publish_type: str | None = None, auto_published: bool | None = None,
        status: str | None = None, limit: int = 100, skip: int = 0,
    ) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if start_date or end_date:
            df: dict[str, str] = {}
            if start_date:
                df["$gte"] = start_date
            if end_date:
                df["$lte"] = end_date
            query["timestamp"] = df
        if publish_type:
            query["publish_type"] = publish_type
        if auto_published is not None:
            query["auto_published"] = auto_published
        if status:
            query["status"] = status

        logs = []
        async for log in self._db.rms_publish_logs.find(query).sort("timestamp", -1).skip(skip).limit(limit):
            log.pop("_id", None)
            logs.append(log)

        total_count = await self._db.rms_publish_logs.count_documents(query)
        return ServiceResult.success({
            "logs": logs, "total_count": total_count,
            "returned_count": len(logs), "skip": skip, "limit": limit,
        })

    # ------------------------------------------------------------------
    # Maintenance Prediction Logs
    # ------------------------------------------------------------------
    async def get_maintenance_prediction_logs(
        self, ctx: OperationContext,
        start_date: str | None = None, end_date: str | None = None,
        equipment_type: str | None = None, prediction_result: str | None = None,
        room_number: str | None = None, limit: int = 100, skip: int = 0,
    ) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if start_date or end_date:
            df: dict[str, str] = {}
            if start_date:
                df["$gte"] = start_date
            if end_date:
                df["$lte"] = end_date
            query["timestamp"] = df
        if equipment_type:
            query["equipment_type"] = equipment_type
        if prediction_result:
            query["prediction_result"] = prediction_result
        if room_number:
            query["room_number"] = room_number

        logs = []
        async for log in self._db.maintenance_prediction_logs.find(query).sort("timestamp", -1).skip(skip).limit(limit):
            log.pop("_id", None)
            logs.append(log)

        total_count = await self._db.maintenance_prediction_logs.count_documents(query)
        risk_stats: dict[str, Any] = {}
        async for doc in self._db.maintenance_prediction_logs.aggregate([
            {"$match": {"tenant_id": ctx.tenant_id}},
            {"$group": {
                "_id": "$prediction_result",
                "count": {"$sum": 1},
                "avg_confidence": {"$avg": "$confidence_score"},
                "tasks_created": {"$sum": {"$cond": ["$auto_task_created", 1, 0]}},
            }},
        ]):
            risk_stats[doc["_id"]] = {
                "count": doc["count"],
                "avg_confidence": round(doc["avg_confidence"], 3),
                "tasks_created": doc["tasks_created"],
            }

        return ServiceResult.success({
            "logs": logs, "total_count": total_count,
            "returned_count": len(logs), "skip": skip, "limit": limit,
            "risk_stats": risk_stats,
        })


night_audit_service = NightAuditService()
