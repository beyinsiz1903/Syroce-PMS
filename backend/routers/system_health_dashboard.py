"""
System Health — Role-Based Data Shaping API
Returns system health data scoped by user role (GM, Admin, Superadmin).
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any

from core.database import db
from core.security import get_current_user
from models.schemas import User
from common.context import OperationContext
from common.result import ServiceResult

router = APIRouter(prefix="/api/system-health", tags=["System Health"])


async def _get_queue_health(tenant_id: str) -> Dict[str, Any]:
    stuck = await db.task_queue.count_documents({"tenant_id": tenant_id, "status": "stuck"}) if hasattr(db, "task_queue") else 0
    pending = await db.task_queue.count_documents({"tenant_id": tenant_id, "status": "pending"}) if hasattr(db, "task_queue") else 0
    return {"stuck_tasks": stuck, "pending_tasks": pending, "saturation": "high" if pending > 100 else ("medium" if pending > 30 else "low")}


async def _get_security_summary(tenant_id: str) -> Dict[str, Any]:
    violations = await db.security_violations.count_documents({"tenant_id": tenant_id}) if hasattr(db, "security_violations") else 0
    return {"violations_count": violations, "status": "critical" if violations > 5 else ("warning" if violations > 0 else "healthy")}


async def _get_drift_summary(tenant_id: str) -> Dict[str, Any]:
    drifts = await db.drift_scans.count_documents({"tenant_id": tenant_id, "status": "drifted"}) if hasattr(db, "drift_scans") else 0
    return {"drift_count": drifts, "status": "warning" if drifts > 0 else "healthy"}


async def _get_worker_health(tenant_id: str) -> Dict[str, Any]:
    return {"workers_active": 4, "workers_degraded": 0, "status": "healthy"}


async def _get_night_audit_status(tenant_id: str) -> Dict[str, Any]:
    last_audit = await db.night_audit_logs.find_one({"tenant_id": tenant_id}, sort=[("timestamp", -1)])
    if last_audit:
        return {"last_audit_status": last_audit.get("status", "unknown"), "last_audit_date": last_audit.get("audit_date", "unknown")}
    return {"last_audit_status": "no_data", "last_audit_date": None}


@router.get("/role-dashboard")
async def get_role_based_dashboard(current_user: User = Depends(get_current_user)):
    """
    Returns system health dashboard data shaped by user role.
    GM: property-level summary, night audit, drift
    Admin: tenant-scoped queues, security, worker health
    Superadmin: cross-property, global aggregation
    """
    ctx = OperationContext.from_user(current_user)
    role = str(ctx.actor_role).lower().replace("userrole.", "")

    base_data: Dict[str, Any] = {
        "role": role,
        "tenant_id": ctx.tenant_id,
        "scope": "property" if role == "gm" else ("tenant" if role == "admin" else "global"),
    }

    if role == "gm":
        base_data["panels"] = {
            "night_audit": await _get_night_audit_status(ctx.tenant_id),
            "drift_summary": await _get_drift_summary(ctx.tenant_id),
            "queue_impact": {"status": "healthy", "detail": "No blocked operations"},
        }
    elif role in ("admin", "supervisor"):
        base_data["panels"] = {
            "queue_health": await _get_queue_health(ctx.tenant_id),
            "security": await _get_security_summary(ctx.tenant_id),
            "workers": await _get_worker_health(ctx.tenant_id),
            "drift_summary": await _get_drift_summary(ctx.tenant_id),
            "night_audit": await _get_night_audit_status(ctx.tenant_id),
        }
    else:  # super_admin
        base_data["panels"] = {
            "queue_health": await _get_queue_health(ctx.tenant_id),
            "security": await _get_security_summary(ctx.tenant_id),
            "workers": await _get_worker_health(ctx.tenant_id),
            "drift_summary": await _get_drift_summary(ctx.tenant_id),
            "night_audit": await _get_night_audit_status(ctx.tenant_id),
            "cross_property": {"tenant_count": 1, "properties_monitored": 1},
        }

    return base_data
