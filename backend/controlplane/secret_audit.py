"""
Secret Access Control — Policy Enforcement + Enhanced Audit
=============================================================
Extends the existing secrets system with:
1. Service-level access policies (which services can access which secrets)
2. Strict tenant isolation at query level
3. Security alert emission on anomalies

Rules:
- No cross-tenant access EVER
- Every access is logged
- No secret values in audit logs
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("controlplane.secret_audit")

COLL_SECRET_AUDIT = "secret_access_audit"

# ── Access Policies ────────────────────────────────────────────────
# Which callers can access which provider secrets.
# format: { caller_pattern: [allowed_providers] }
# "*" means all providers
DEFAULT_ACCESS_POLICIES = {
    "channel_manager": ["exely", "hotelrunner", "*"],
    "import_bridge": ["exely", "hotelrunner"],
    "ari_push": ["exely", "hotelrunner"],
    "credential_vault": ["*"],
    "system": ["*"],
    "operator": ["*"],
    "migration": ["*"],
}


def check_access_policy(
    caller: str,
    provider: str,
) -> bool:
    """Check if a caller is allowed to access secrets for a provider.

    Returns True if access is allowed, False if denied.
    """
    allowed = DEFAULT_ACCESS_POLICIES.get(caller)
    if allowed is None:
        # Unknown caller — deny by default
        return False
    if "*" in allowed:
        return True
    return provider in allowed


class SecretAccessControl:
    """Enhanced secret access control with policy enforcement and alerting."""

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
        provider: str,
        property_id: str = "",
        access_type: str,
        caller: str,
        result: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a secret access event. NO secret values stored."""
        db = self._get_db()
        record = {
            "tenant_id": tenant_id,
            "provider": provider,
            "property_id": property_id,
            "access_type": access_type,
            "caller": caller,
            "result": result,
            "reason": reason,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await db[COLL_SECRET_AUDIT].insert_one(record)
        except Exception:
            logger.exception("Failed to write secret access audit log")

        # Emit failure event for denied access
        if result in ("denied", "failure"):
            await self._emit_security_failure(
                tenant_id=tenant_id,
                provider=provider,
                access_type=access_type,
                caller=caller,
                result=result,
                reason=reason,
            )

    async def check_and_log(
        self,
        *,
        tenant_id: str,
        provider: str,
        property_id: str = "",
        access_type: str,
        caller: str,
        request_tenant_id: Optional[str] = None,
    ) -> bool:
        """Check access policy and log the result.

        Returns True if access is allowed, False if denied.
        Automatically logs the attempt.
        """
        # Tenant isolation: deny cross-tenant access
        if request_tenant_id and request_tenant_id != tenant_id:
            await self.log_access(
                tenant_id=tenant_id,
                provider=provider,
                property_id=property_id,
                access_type=access_type,
                caller=caller,
                result="denied",
                reason=f"Cross-tenant access denied: request_tenant={request_tenant_id}, target_tenant={tenant_id}",
            )
            logger.critical(
                "SECURITY: Cross-tenant secret access DENIED caller=%s req_tenant=%s target_tenant=%s",
                caller, request_tenant_id, tenant_id,
            )
            return False

        # Policy check
        allowed = check_access_policy(caller, provider)
        if not allowed:
            await self.log_access(
                tenant_id=tenant_id,
                provider=provider,
                property_id=property_id,
                access_type=access_type,
                caller=caller,
                result="denied",
                reason=f"Access policy denied: caller={caller} is not allowed to access provider={provider}",
            )
            logger.warning(
                "SECURITY: Secret access DENIED by policy caller=%s provider=%s tenant=%s",
                caller, provider, tenant_id,
            )
            return False

        # Log success
        await self.log_access(
            tenant_id=tenant_id,
            provider=provider,
            property_id=property_id,
            access_type=access_type,
            caller=caller,
            result="success",
        )
        return True

    async def get_audit_trail(
        self,
        *,
        tenant_id: Optional[str] = None,
        provider: Optional[str] = None,
        result_filter: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """Get audit trail with filters and pagination."""
        query: Dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if provider:
            query["provider"] = provider
        if result_filter:
            query["result"] = result_filter

        db = self._get_db()
        coll = db[COLL_SECRET_AUDIT]
        total = await coll.count_documents(query)
        items = await coll.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)

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
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get secret access anomalies (failures, denials)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        query: Dict[str, Any] = {
            "result": {"$in": ["failure", "denied", "not_found"]},
            "timestamp": {"$gte": cutoff},
        }
        if tenant_id:
            query["tenant_id"] = tenant_id

        db = self._get_db()
        coll = db[COLL_SECRET_AUDIT]
        count = await coll.count_documents(query)
        items = await coll.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).limit(20).to_list(20)

        return {
            "anomaly_count": count,
            "recent_anomalies": items,
            "window_hours": hours,
        }

    async def _emit_security_failure(
        self,
        *,
        tenant_id: str,
        provider: str,
        access_type: str,
        caller: str,
        result: str,
        reason: str,
    ) -> None:
        """Emit a failure event to the control plane failure tracker."""
        try:
            from controlplane.failure_tracker import get_failure_tracker
            from controlplane.failure_model import FailureType, Severity
            tracker = get_failure_tracker()
            await tracker.record(
                tenant_id=tenant_id,
                provider=provider,
                operation_type="secret_access",
                error_code=f"SECRET_{result.upper()}",
                error_message=reason or f"Secret access {result}: {access_type} by {caller}",
                failure_type=FailureType.SECURITY_ERROR,
                severity=Severity.CRITICAL,
                context={
                    "access_type": access_type,
                    "caller": caller,
                    "result": result,
                },
            )
        except Exception:
            logger.exception("Failed to emit secret access failure event")


# ── Singleton ──────────────────────────────────────────────────────
_access_control: Optional[SecretAccessControl] = None


def get_secret_access_control() -> SecretAccessControl:
    global _access_control
    if _access_control is None:
        _access_control = SecretAccessControl()
    return _access_control
