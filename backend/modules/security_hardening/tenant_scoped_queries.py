"""
Tenant-Scoped Queries - Query guards to enforce tenant data isolation.
Every database query must pass through tenant context validation.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from core.database import db

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
        self._violations: List[dict] = []
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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
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

    async def check_isolation(self, tenant_id: str) -> Dict[str, Any]:
        """Run isolation checks for a tenant."""
        results = []
        for coll_name in TENANT_SCOPED_COLLECTIONS:
            coll = db[coll_name]
            total = await coll.count_documents({"tenant_id": tenant_id})
            # Check for documents without tenant_id
            unscoped = await coll.count_documents({"tenant_id": {"$exists": False}})
            results.append({
                "collection": coll_name,
                "tenant_documents": total,
                "unscoped_documents": unscoped,
                "isolation_status": "clean" if unscoped == 0 else "warning",
            })

        clean_count = sum(1 for r in results if r["isolation_status"] == "clean")
        return {
            "tenant_id": tenant_id,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "collections_checked": len(results),
            "clean_collections": clean_count,
            "isolation_score": round(clean_count / max(len(results), 1), 4),
            "details": results,
            "total_checks_performed": self._checks_performed,
            "total_violations_blocked": self._violations_blocked,
        }

    def get_violations(self, limit: int = 50) -> List[dict]:
        return self._violations[-limit:]


tenant_query_guard = TenantQueryGuard()
