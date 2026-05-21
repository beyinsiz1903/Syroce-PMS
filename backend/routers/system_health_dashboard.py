"""
System Health — Role-Based Data Shaping API (Enriched)
Returns real system health data scoped by user role (GM, Admin, Superadmin).
"""
import asyncio
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
    if not hasattr(db, "task_queue"):
        stuck = pending = processing = failed = 0
    else:
        # Perf: 4 sıralı count → tek gather
        stuck, pending, processing, failed = await asyncio.gather(
            db.task_queue.count_documents({"tenant_id": tenant_id, "status": "stuck"}),
            db.task_queue.count_documents({"tenant_id": tenant_id, "status": "pending"}),
            db.task_queue.count_documents({"tenant_id": tenant_id, "status": "processing"}),
            db.task_queue.count_documents({"tenant_id": tenant_id, "status": "failed"}),
        )
    return {
        "stuck_tasks": stuck,
        "pending_tasks": pending,
        "processing": processing,
        "failed": failed,
        "saturation": "high" if pending > 100 else ("medium" if pending > 30 else "low"),
        "severity": "critical" if stuck > 5 else ("warning" if stuck > 0 or pending > 50 else "info"),
    }


async def _get_security_summary(tenant_id: str) -> dict[str, Any]:
    if not hasattr(db, "tenant_guard_violations"):
        violations = recent = 0
    else:
        # Perf: 2 sıralı count → tek gather
        violations, recent = await asyncio.gather(
            db.tenant_guard_violations.count_documents({"expected_tenant_id": tenant_id}),
            db.tenant_guard_violations.count_documents({
                "expected_tenant_id": tenant_id,
                "timestamp": {"$gte": (datetime.now(UTC) - timedelta(hours=24)).isoformat()},
            }),
        )
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
    # Perf: 2 sıralı count → tek gather
    recent_activity, dl_total = await asyncio.gather(
        db.task_queue.count_documents({
            "status": "completed",
            "started_at": {"$gte": (datetime.now(UTC) - timedelta(minutes=10)).isoformat()},
        }),
        db.dead_letter_tasks.count_documents({}),
    )
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
    # Perf: 2 sıralı count → tek gather
    total, failed = await asyncio.gather(
        db.channel_sync_logs.count_documents({"tenant_id": tenant_id, "timestamp": {"$gte": last_24h}}),
        db.channel_sync_logs.count_documents({"tenant_id": tenant_id, "timestamp": {"$gte": last_24h}, "status": "error"}),
    )
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

    # Perf: panel build'lerini paralel topla — her panel kendi içinde de paralel
    if role == "gm":
        night, drift, sync = await asyncio.gather(
            _get_night_audit_status(tenant_id),
            _get_drift_summary(tenant_id),
            _get_sync_summary(tenant_id),
        )
        base_data["panels"] = {
            "night_audit": night,
            "drift_summary": drift,
            "sync_summary": sync,
            "queue_impact": {"status": "healthy", "detail": "No blocked operations"},
        }
    elif role in ("admin", "supervisor"):
        queue, sec, work, drift, sync, night = await asyncio.gather(
            _get_queue_health(tenant_id),
            _get_security_summary(tenant_id),
            _get_worker_health(tenant_id),
            _get_drift_summary(tenant_id),
            _get_sync_summary(tenant_id),
            _get_night_audit_status(tenant_id),
        )
        base_data["panels"] = {
            "queue_health": queue,
            "security": sec,
            "workers": work,
            "drift_summary": drift,
            "sync_summary": sync,
            "night_audit": night,
        }
    else:  # super_admin or other
        queue, sec, work, drift, sync, night = await asyncio.gather(
            _get_queue_health(tenant_id),
            _get_security_summary(tenant_id),
            _get_worker_health(tenant_id),
            _get_drift_summary(tenant_id),
            _get_sync_summary(tenant_id),
            _get_night_audit_status(tenant_id),
        )
        base_data["panels"] = {
            "queue_health": queue,
            "security": sec,
            "workers": work,
            "drift_summary": drift,
            "sync_summary": sync,
            "night_audit": night,
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
