"""
Tenant-Scoped Queries - Query guards to enforce tenant data isolation.
Every database query must pass through tenant context validation.
"""
import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import _raw_db

logger = logging.getLogger("security.tenant_queries")

TENANT_SCOPED_COLLECTIONS = [
    "bookings", "guests", "rooms", "folios", "tasks", "users",
    "invoices", "audit_logs", "messaging_delivery_logs",
    "ml_predictions", "pipeline_runs", "revenue_approval_queue",
    "feature_store", "ml_datasets", "model_registry",
    "event_bus_log", "messaging_provider_configs",
]


class TenantQueryGuard:
    """Validates and enforces tenant-scoped database queries."""

    def __init__(self):
        self._violations: list[dict] = []
        self._checks_performed = 0
        self._violations_blocked = 0

    def validate_query(self, collection: str, query: dict, tenant_id: str,
                       operation: str = "read") -> dict:
        """Validate that a query is properly tenant-scoped."""
        self._checks_performed += 1
        result = {
            "collection": collection,
            "operation": operation,
            "tenant_id": tenant_id,
            "valid": True,
            "warnings": [],
        }

        if collection in TENANT_SCOPED_COLLECTIONS:
            if "tenant_id" not in query:
                result["valid"] = False
                result["warnings"].append(
                    f"Query to '{collection}' missing tenant_id filter"
                )
                self._violations_blocked += 1
                self._violations.append({
                    "collection": collection,
                    "operation": operation,
                    "expected_tenant": tenant_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
            elif query.get("tenant_id") != tenant_id:
                result["valid"] = False
                result["warnings"].append(
                    "Cross-tenant access attempt: query tenant_id does not match context"
                )
                self._violations_blocked += 1

        return result

    def enforce_tenant_filter(self, query: dict, tenant_id: str) -> dict:
        """Add tenant_id to a query if missing."""
        if "tenant_id" not in query:
            query["tenant_id"] = tenant_id
        return query

    async def check_isolation(self, tenant_id: str) -> dict[str, Any]:
        """Run isolation checks for a tenant. Uses raw DB to bypass tenant guard.

        Perf: 17 koleksiyon × 2 sıralı count_documents = 34 sıralı Atlas RTT
        (~4.7 sn ölçüldü) → tek asyncio.gather ile ~1-2 RTT'ye iner.
        """
        coros: list = []
        for coll_name in TENANT_SCOPED_COLLECTIONS:
            coll = _raw_db[coll_name]
            coros.append(coll.count_documents({"tenant_id": tenant_id}))
            coros.append(coll.count_documents({"tenant_id": {"$exists": False}}))

        counts = await asyncio.gather(*coros)

        results = []
        for idx, coll_name in enumerate(TENANT_SCOPED_COLLECTIONS):
            total = counts[idx * 2]
            unscoped = counts[idx * 2 + 1]
            results.append({
                "collection": coll_name,
                "tenant_documents": total,
                "unscoped_documents": unscoped,
                "isolation_status": "clean" if unscoped == 0 else "warning",
            })

        clean_count = sum(1 for r in results if r["isolation_status"] == "clean")
        return {
            "tenant_id": tenant_id,
            "checked_at": datetime.now(UTC).isoformat(),
            "collections_checked": len(results),
            "clean_collections": clean_count,
            "isolation_score": round(clean_count / max(len(results), 1), 4),
            "details": results,
            "total_checks_performed": self._checks_performed,
            "total_violations_blocked": self._violations_blocked,
        }

    def get_violations(self, limit: int = 50) -> list[dict]:
        return self._violations[-limit:]


tenant_query_guard = TenantQueryGuard()
