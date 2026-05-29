"""
Secret access audit logging.

Writes audit records to MongoDB `secret_access_audit` collection.
Never stores plaintext secret values. Records who/what/when/result.
"""
import logging
from datetime import UTC, datetime
from typing import Any

from core.transient_db_guard import TransientFailureTracker

logger = logging.getLogger("core.secrets.audit")

_transient_tracker = TransientFailureTracker("secret-audit")

COLL_SECRET_AUDIT = "secret_access_audit"


class SecretAuditLogger:
    """Writes secret-access audit events to MongoDB."""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled

    def _get_db(self):
        # Use raw db (not TenantAwareDBProxy) — system audit logs must remain
        # globally queryable, never auto-scoped by tenant context.
        from core.database import _raw_db as db
        return db

    async def log(
        self,
        action: str,
        secret_path: str,
        result: str,
        *,
        tenant_id: str = "",
        provider: str = "",
        property_id: str = "",
        actor: str = "system",
        error_class: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Record a secret access event.

        action: create | read | update | delete | rotate | metadata_read
        result: success | failure | not_found | denied
        """
        if not self._enabled:
            return

        record = {
            "action": action,
            "secret_path": secret_path,
            "result": result,
            "tenant_id": tenant_id,
            "provider": provider,
            "property_id": property_id,
            "actor": actor,
            "error_class": error_class,
            "metadata": metadata or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            db = self._get_db()
            await db[COLL_SECRET_AUDIT].insert_one(record)
            _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
        except Exception as exc:
            # Audit failure must not break secret operations. Transient Atlas
            # hiccups (no-primary / SSL handshake timeout) are demoted to
            # WARNING until the streak hits threshold, then escalate to ERROR so
            # a sustained outage stays visible; real bugs keep ERROR+traceback.
            _transient_tracker.log_exception(
                logger,
                exc,
                TransientFailureTracker.OUTER_LOOP_KEY,
                context="secret audit write",
                non_transient_msg="%s failed to write secret audit log: %s",
            )

    async def get_audit_trail(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list:
        """Retrieve recent audit trail for a tenant."""
        db = self._get_db()
        records = await db[COLL_SECRET_AUDIT].find(
            {"tenant_id": tenant_id},
            {"_id": 0},
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        return records

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient audit queries."""
        db = self._get_db()
        coll = db[COLL_SECRET_AUDIT]
        await coll.create_index([("tenant_id", 1), ("timestamp", -1)])
        await coll.create_index([("secret_path", 1), ("timestamp", -1)])
        await coll.create_index([("action", 1), ("timestamp", -1)])
        await coll.create_index("timestamp", expireAfterSeconds=90 * 86400)  # 90-day TTL
