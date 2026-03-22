"""
Security — Tenant Guard
Enforces tenant isolation at the query/response level.
Ensures no cross-tenant data leakage.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from core.tenant_db import LazyCollection

logger = logging.getLogger(__name__)


class TenantGuard:
    """Validates and enforces tenant-scoped data access."""

    _violation_log_collection = LazyCollection("tenant_guard_violations")

    @classmethod
    async def validate_query(
        cls,
        query: Dict[str, Any],
        expected_tenant_id: str,
    ) -> Dict[str, Any]:
        """Validate that a DB query is properly scoped to the expected tenant."""
        query_tenant = query.get("tenant_id")
        if not query_tenant:
            return {
                "valid": False,
                "violation": "missing_tenant_id",
                "message": "Query does not contain tenant_id filter",
            }
        if query_tenant != expected_tenant_id:
            await cls._log_violation(
                expected_tenant_id, query_tenant, "tenant_mismatch"
            )
            return {
                "valid": False,
                "violation": "tenant_mismatch",
                "message": f"Query tenant {query_tenant} does not match session {expected_tenant_id}",
            }
        return {"valid": True}

    @classmethod
    async def validate_response(
        cls,
        documents: List[Dict[str, Any]],
        expected_tenant_id: str,
    ) -> Dict[str, Any]:
        """Validate that all returned documents belong to the expected tenant."""
        violations = []
        for i, doc in enumerate(documents):
            doc_tenant = doc.get("tenant_id")
            if doc_tenant and doc_tenant != expected_tenant_id:
                violations.append({
                    "index": i,
                    "doc_tenant": doc_tenant,
                    "expected_tenant": expected_tenant_id,
                })
        if violations:
            await cls._log_violation(
                expected_tenant_id,
                str([v["doc_tenant"] for v in violations]),
                "response_leak",
            )
            return {
                "valid": False,
                "violations": violations,
                "leaked_count": len(violations),
            }
        return {"valid": True, "checked_count": len(documents)}

    @classmethod
    async def get_status(cls, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get tenant guard enforcement status and violation counts."""
        query: Dict[str, Any] = {}
        if tenant_id:
            query["expected_tenant_id"] = tenant_id

        total_violations = await cls._violation_log_collection.count_documents(query)

        last_24h = (datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=24)).isoformat()
        recent_violations = await cls._violation_log_collection.count_documents({
            **query,
            "timestamp": {"$gte": last_24h},
        })

        recent = await cls._violation_log_collection.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).limit(10).to_list(10)

        return {
            "enforcement": "active",
            "total_violations": total_violations,
            "violations_last_24h": recent_violations,
            "recent_violations": recent,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    async def _log_violation(
        cls, expected_tenant: str, actual_tenant: str, violation_type: str,
    ) -> None:
        logger.warning(
            f"Tenant guard violation: type={violation_type} "
            f"expected={expected_tenant} actual={actual_tenant}"
        )
        await cls._violation_log_collection.insert_one({
            "expected_tenant_id": expected_tenant,
            "actual_tenant_id": actual_tenant,
            "violation_type": violation_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


tenant_guard = TenantGuard()
