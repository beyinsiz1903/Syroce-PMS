"""
Failure Tracker — Centralized Failure Recording and Resolution
===============================================================
Single entry point for recording, querying, and resolving failures.
Every subsystem (outbox, import, sync, secrets) calls this service.

Multi-tenant aware. Provider-aware. Never leaks plaintext.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .failure_model import (
    FailureStatus,
    FailureType,
    Severity,
    build_failure_event,
    classify_failure,
    resolve_severity,
)

logger = logging.getLogger("controlplane.failure_tracker")

COLL_FAILURES = "cp_failures"


class FailureTracker:
    """Central failure tracking service.

    Usage:
        tracker = get_failure_tracker()
        await tracker.record(
            tenant_id="t1", provider="exely",
            operation_type="reservation_import",
            error_code="IMPORT_TIMEOUT",
            error_message="Connection timed out after 30s",
        )
    """

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            from core.database import db
            self._db = db
        return self._db

    async def record(
        self,
        *,
        tenant_id: str,
        provider: str,
        operation_type: str,
        error_code: str,
        error_message: str,
        failure_type: Optional[FailureType] = None,
        severity: Optional[Severity] = None,
        context: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
        correlation_id: Optional[str] = None,
        property_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a structured failure event.

        If failure_type is not provided, it will be auto-classified
        from the error_message using the taxonomy keywords.
        """
        if failure_type is None:
            failure_type = classify_failure(error_message, operation_type=operation_type)

        if severity is None:
            severity = resolve_severity(failure_type)

        event = build_failure_event(
            tenant_id=tenant_id,
            provider=provider,
            operation_type=operation_type,
            failure_type=failure_type,
            error_code=error_code,
            error_message=error_message,
            severity=severity,
            context=context,
            retry_count=retry_count,
            correlation_id=correlation_id,
            property_id=property_id,
        )

        db = self._get_db()
        await db[COLL_FAILURES].insert_one({**event})
        logger.warning(
            "Failure recorded: op=%s type=%s sev=%s tenant=%s provider=%s code=%s",
            operation_type, failure_type.value, severity.value,
            tenant_id, provider, error_code,
        )
        return event

    async def list_failures(
        self,
        *,
        tenant_id: Optional[str] = None,
        provider: Optional[str] = None,
        failure_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        operation_type: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """List failures with filters and pagination."""
        query: Dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if provider:
            query["provider"] = provider
        if failure_type:
            query["failure_type"] = failure_type
        if severity:
            query["severity"] = severity
        if status:
            query["status"] = status
        if operation_type:
            query["operation_type"] = operation_type

        db = self._get_db()
        coll = db[COLL_FAILURES]
        total = await coll.count_documents(query)
        items = await coll.find(
            query, {"_id": 0}
        ).sort("last_seen_at", -1).skip(skip).limit(limit).to_list(limit)

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "skip": skip,
        }

    async def get_failure(self, failure_id: str) -> Optional[Dict[str, Any]]:
        """Get a single failure by ID."""
        db = self._get_db()
        return await db[COLL_FAILURES].find_one(
            {"id": failure_id}, {"_id": 0}
        )

    async def resolve(self, failure_id: str, *, resolved_by: str = "operator") -> bool:
        """Mark a failure as resolved."""
        db = self._get_db()
        result = await db[COLL_FAILURES].update_one(
            {"id": failure_id, "status": {"$ne": FailureStatus.RESOLVED.value}},
            {"$set": {
                "status": FailureStatus.RESOLVED.value,
                "resolved_by": resolved_by,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return result.modified_count == 1

    async def ignore(self, failure_id: str, *, ignored_by: str = "operator") -> bool:
        """Mark a failure as ignored (acknowledged, won't fix)."""
        db = self._get_db()
        result = await db[COLL_FAILURES].update_one(
            {"id": failure_id, "status": {"$ne": FailureStatus.IGNORED.value}},
            {"$set": {
                "status": FailureStatus.IGNORED.value,
                "ignored_by": ignored_by,
                "ignored_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return result.modified_count == 1

    async def mark_retrying(self, failure_id: str) -> bool:
        """Mark a failure as being retried."""
        db = self._get_db()
        result = await db[COLL_FAILURES].update_one(
            {"id": failure_id, "status": FailureStatus.OPEN.value},
            {"$set": {
                "status": FailureStatus.RETRYING.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$inc": {"retry_count": 1}},
        )
        return result.modified_count == 1

    async def reopen(self, failure_id: str, *, error_message: str = "") -> bool:
        """Reopen a failure after a retry attempt fails."""
        now = datetime.now(timezone.utc).isoformat()
        update: Dict[str, Any] = {
            "$set": {
                "status": FailureStatus.OPEN.value,
                "last_seen_at": now,
                "updated_at": now,
            }
        }
        if error_message:
            update["$set"]["error_message"] = error_message
        db = self._get_db()
        result = await db[COLL_FAILURES].update_one(
            {"id": failure_id}, update,
        )
        return result.modified_count == 1

    # ── Aggregation Queries ────────────────────────────────────────

    async def count_open(self, *, tenant_id: Optional[str] = None) -> int:
        """Count open (unresolved) failures."""
        query: Dict[str, Any] = {"status": FailureStatus.OPEN.value}
        if tenant_id:
            query["tenant_id"] = tenant_id
        db = self._get_db()
        return await db[COLL_FAILURES].count_documents(query)

    async def count_by_severity(self, *, tenant_id: Optional[str] = None) -> Dict[str, int]:
        """Count open failures grouped by severity."""
        match: Dict[str, Any] = {"status": FailureStatus.OPEN.value}
        if tenant_id:
            match["tenant_id"] = tenant_id

        db = self._get_db()
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]
        result = {}
        async for doc in db[COLL_FAILURES].aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        return result

    async def count_by_type(self, *, tenant_id: Optional[str] = None) -> Dict[str, int]:
        """Count open failures grouped by failure_type."""
        match: Dict[str, Any] = {"status": FailureStatus.OPEN.value}
        if tenant_id:
            match["tenant_id"] = tenant_id

        db = self._get_db()
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$failure_type", "count": {"$sum": 1}}},
        ]
        result = {}
        async for doc in db[COLL_FAILURES].aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        return result

    async def count_by_operation(self, *, tenant_id: Optional[str] = None) -> Dict[str, int]:
        """Count open failures grouped by operation_type."""
        match: Dict[str, Any] = {"status": FailureStatus.OPEN.value}
        if tenant_id:
            match["tenant_id"] = tenant_id

        db = self._get_db()
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$operation_type", "count": {"$sum": 1}}},
        ]
        result = {}
        async for doc in db[COLL_FAILURES].aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        return result

    async def recent_failures(
        self, *, hours: int = 24, tenant_id: Optional[str] = None, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent failures within a time window."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        query: Dict[str, Any] = {"created_at": {"$gte": cutoff}}
        if tenant_id:
            query["tenant_id"] = tenant_id

        db = self._get_db()
        return await db[COLL_FAILURES].find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)


# ── Singleton ──────────────────────────────────────────────────────
_tracker: Optional[FailureTracker] = None


def get_failure_tracker() -> FailureTracker:
    global _tracker
    if _tracker is None:
        _tracker = FailureTracker()
    return _tracker
