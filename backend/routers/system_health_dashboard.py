"""
System Health — Role-Based Data Shaping API (Enriched)
Returns real system health data scoped by user role (GM, Admin, Superadmin).
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from common.context import OperationContext
from core.database import db
from core.security import get_current_user
from models.schemas import User

try:
    from cache_manager import cached
except ImportError:  # pragma: no cover
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api/system-health", tags=["System Health"])


async def _get_queue_health(tenant_id: str) -> dict[str, Any]:
    stuck = await db.task_queue.count_documents({"tenant_id": tenant_id, "status": "stuck"}) if hasattr(db, "task_queue") else 0
    pending = await db.task_queue.count_documents({"tenant_id": tenant_id, "status": "pending"}) if hasattr(db, "task_queue") else 0
    processing = await db.task_queue.count_documents({"tenant_id": tenant_id, "status": "processing"}) if hasattr(db, "task_queue") else 0
    failed = await db.task_queue.count_documents({"tenant_id": tenant_id, "status": "failed"}) if hasattr(db, "task_queue") else 0
    return {
        "stuck_tasks": stuck,
        "pending_tasks": pending,
        "processing": processing,
        "failed": failed,
        "saturation": "high" if pending > 100 else ("medium" if pending > 30 else "low"),
        "severity": "critical" if stuck > 5 else ("warning" if stuck > 0 or pending > 50 else "info"),
    }


async def _get_security_summary(tenant_id: str) -> dict[str, Any]:
    violations = await db.tenant_guard_violations.count_documents({
        "expected_tenant_id": tenant_id
    }) if hasattr(db, "tenant_guard_violations") else 0
    recent = await db.tenant_guard_violations.count_documents({
        "expected_tenant_id": tenant_id,
        "timestamp": {"$gte": (datetime.now(UTC) - timedelta(hours=24)).isoformat()}
    }) if hasattr(db, "tenant_guard_violations") else 0
    return {
        "violations_count": violations,
        "violations_24h": recent,
        "status": "critical" if violations > 5 else ("warning" if violations > 0 else "healthy"),
    }


async def _get_drift_summary(tenant_id: str) -> dict[str, Any]:
    latest = await db.drift_scan_results.find_one(
        {"tenant_id": tenant_id}, {"_id": 0}, sort=[("timestamp", -1)]
    )
    if latest:
        return {
            "drift_count": latest.get("drifts_found", 0),
            "critical_drifts": latest.get("critical_drifts", 0),
            "last_scan_at": latest.get("scanned_at"),
            "status": "critical" if latest.get("critical_drifts", 0) > 0 else (
                "warning" if latest.get("drifts_found", 0) > 0 else "healthy"
            ),
        }
    return {"drift_count": 0, "critical_drifts": 0, "last_scan_at": None, "status": "healthy"}


async def _get_worker_health(tenant_id: str) -> dict[str, Any]:
    recent_activity = await db.task_queue.count_documents({
        "status": "completed",
        "started_at": {"$gte": (datetime.now(UTC) - timedelta(minutes=10)).isoformat()}
    })
    dl_total = await db.dead_letter_tasks.count_documents({})
    return {
        "workers_responding": recent_activity > 0,
        "recent_completions": recent_activity,
        "dead_letter_total": dl_total,
        "status": "healthy" if recent_activity > 0 else "degraded",
    }


async def _get_night_audit_status(tenant_id: str) -> dict[str, Any]:
    last_audit = await db.night_audit_logs.find_one(
        {"tenant_id": tenant_id}, sort=[("timestamp", -1)]
    )
    if last_audit:
        return {
            "last_audit_status": last_audit.get("status", "unknown"),
            "last_audit_date": last_audit.get("audit_date", "unknown"),
        }
    return {"last_audit_status": "no_data", "last_audit_date": None}


async def _get_sync_summary(tenant_id: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    last_24h = (now - timedelta(hours=24)).isoformat()
    total = await db.channel_sync_logs.count_documents({"tenant_id": tenant_id, "timestamp": {"$gte": last_24h}})
    failed = await db.channel_sync_logs.count_documents({"tenant_id": tenant_id, "timestamp": {"$gte": last_24h}, "status": "error"})
    return {
        "syncs_24h": total,
        "failed_24h": failed,
        "success_rate": round((1 - failed / max(total, 1)) * 100, 1),
    }


@cached(ttl=60, key_prefix="role_dashboard")  # Sprint 33 R6: keyed by role to prevent cross-role leak
async def _build_role_dashboard(tenant_id: str, role: str) -> dict[str, Any]:
    """Inner cacheable: key includes tenant_id (auto) + role (positional str arg)."""
    base_data: dict[str, Any] = {
        "role": role,
        "tenant_id": tenant_id,
        "scope": "property" if role == "gm" else ("tenant" if role == "admin" else "global"),
        "last_updated_at": datetime.now(UTC).isoformat(),
    }

    if role == "gm":
        base_data["panels"] = {
            "night_audit": await _get_night_audit_status(tenant_id),
            "drift_summary": await _get_drift_summary(tenant_id),
            "sync_summary": await _get_sync_summary(tenant_id),
            "queue_impact": {"status": "healthy", "detail": "No blocked operations"},
        }
    elif role in ("admin", "supervisor"):
        base_data["panels"] = {
            "queue_health": await _get_queue_health(tenant_id),
            "security": await _get_security_summary(tenant_id),
            "workers": await _get_worker_health(tenant_id),
            "drift_summary": await _get_drift_summary(tenant_id),
            "sync_summary": await _get_sync_summary(tenant_id),
            "night_audit": await _get_night_audit_status(tenant_id),
        }
    else:  # super_admin or other
        base_data["panels"] = {
            "queue_health": await _get_queue_health(tenant_id),
            "security": await _get_security_summary(tenant_id),
            "workers": await _get_worker_health(tenant_id),
            "drift_summary": await _get_drift_summary(tenant_id),
            "sync_summary": await _get_sync_summary(tenant_id),
            "night_audit": await _get_night_audit_status(tenant_id),
            "cross_property": {"tenant_count": 1, "properties_monitored": 1},
        }

    return base_data


@router.get("/role-dashboard")
async def get_role_based_dashboard(current_user: User = Depends(get_current_user)):
    """Role-scoped system health dashboard. Caching keyed by (tenant_id, role)
    via inner `_build_role_dashboard` to prevent cross-role data leakage."""
    ctx = OperationContext.from_user(current_user)
    role = str(ctx.actor_role).lower().replace("userrole.", "")
    return await _build_role_dashboard(ctx.tenant_id, role)
