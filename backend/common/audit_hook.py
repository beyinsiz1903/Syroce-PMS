"""
Common — Audit Hook Decorator
Service-level audit decorator for consistent audit trail generation.
Wraps service methods to automatically log audit events.
"""
import functools
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Callable

logger = logging.getLogger(__name__)

# Standard severity levels
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


async def _write_audit(db, entry: dict):
    """Persist audit entry (tamper-evident chain). Silently log on failure —
    never break the caller."""
    try:
        from core.audit_chain import append_audit_log
        await append_audit_log(db, entry)
    except Exception as exc:
        logger.warning("audit_hook: write failed — %s", exc)


def audited(
    operation_name: str,
    target_type: str,
    severity: str = SEVERITY_INFO,
    capture_before: bool = False,
    require_reason: bool = False,
):
    """
    Decorator for service methods that require audit trail.

    The decorated method MUST have signature:
        async def method(self, ctx: OperationContext, ...) -> ServiceResult

    Parameters
    ----------
    operation_name : str   — e.g. "pos.create_transaction"
    target_type    : str   — e.g. "pos_transaction", "booking"
    severity       : str   — info | warning | critical
    capture_before : bool  — if True, will snapshot target before mutation
    require_reason : bool  — if True, kwargs must contain 'reason'
    """

    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(self, ctx, *args, **kwargs):
            from common.result import ServiceResult

            # Enforce reason for critical operations
            if require_reason and not kwargs.get("reason"):
                return ServiceResult.fail(
                    f"Operation '{operation_name}' requires a reason",
                    "REASON_REQUIRED",
                )

            correlation_id = getattr(ctx, "correlation_id", None) or str(uuid.uuid4())
            start_ts = time.monotonic()

            # Optional before-snapshot
            before_snapshot = None
            if capture_before:
                target_id = kwargs.get("target_id") or (args[0] if args else None)
                if target_id and hasattr(self, "_db"):
                    col_name = _collection_for(target_type)
                    if col_name:
                        doc = await self._db[col_name].find_one(
                            {"id": target_id, "tenant_id": ctx.tenant_id},
                            {"_id": 0},
                        )
                        before_snapshot = doc

            # Execute the actual service method
            result = await fn(self, ctx, *args, **kwargs)

            duration_ms = int((time.monotonic() - start_ts) * 1000)

            # Determine target_id from result or args
            target_id = None
            if args:
                target_id = str(args[0])
            if result.ok and isinstance(result.data, dict):
                target_id = result.data.get("id") or result.data.get("booking_id") or target_id

            # Build after-snapshot from result data
            after_snapshot = None
            if result.ok and capture_before and isinstance(result.data, dict):
                after_snapshot = result.data

            audit_entry = {
                "id": str(uuid.uuid4()),
                "tenant_id": ctx.tenant_id,
                "property_id": getattr(ctx, "property_id", None),
                "actor_id": ctx.actor_id,
                "actor_role": getattr(ctx, "actor_role", ""),
                "service_name": self.__class__.__name__,
                "operation_name": operation_name,
                "target_type": target_type,
                "target_id": target_id,
                "result_status": "success" if result.ok else "failure",
                "error_code": result.code if not result.ok else None,
                "severity": severity,
                "before_snapshot": before_snapshot,
                "after_snapshot": after_snapshot,
                "override_reason": kwargs.get("reason"),
                "correlation_id": correlation_id,
                "duration_ms": duration_ms,
                "ip_address": getattr(ctx, "ip_address", None),
                "user_agent": getattr(ctx, "user_agent", None),
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Write audit asynchronously (fire-and-forget style)
            if hasattr(self, "_db"):
                await _write_audit(self._db, audit_entry)

            return result

        return wrapper

    return decorator


def _collection_for(target_type: str) -> str | None:
    """Map target_type to MongoDB collection name for before-snapshots."""
    mapping = {
        "booking": "bookings",
        "reservation": "bookings",
        "room": "rooms",
        "guest": "guests",
        "folio": "folios",
        "folio_charge": "folio_charges",
        "payment": "payments",
        "pos_transaction": "pos_transactions",
        "pos_order": "pos_orders",
        "kitchen_order": "kitchen_orders",
        "inventory": "inventory",
        "housekeeping_task": "housekeeping_tasks",
        "maintenance_task": "tasks",
        "group_booking": "group_bookings",
        "corporate_contract": "corporate_contracts",
        "ota_promotion": "ota_promotions",
        "keycard": "keycards",
        "rate_calendar": "rate_calendar",
    }
    return mapping.get(target_type)
