"""
Wire Failure Tracking Router
Kanal yoneticisi hata takip sistemi.
ARI push hatalari, sync hatalari, DLQ kayitlarini takip eder.
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from cache_manager import cached
from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/wire-failures", tags=["Wire Failure Tracking"])


@router.get("/summary")
@cached(ttl=60, key_prefix="wire_failures_summary")
async def get_failure_summary(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get wire failure summary across all providers."""
    tenant_id = current_user.tenant_id
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    # ARI hard fail log
    ari_fails = await db.ari_hard_fail_log.count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": cutoff},
    })

    # Exely sync failures
    exely_fails = await db.exely_sync_logs.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["failed", "error"]},
        "timestamp": {"$gte": cutoff},
    })

    # Connector outbox failures (DLQ)
    dlq_count = await db.connector_outbox.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["failed", "dead_letter"]},
    })

    # CP failures
    cp_fails = await db.cp_failures.count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": cutoff},
    })

    # Reconciliation issues
    recon_issues = await db.cm_reconciliation_issues.count_documents({
        "tenant_id": tenant_id,
        "status": {"$ne": "resolved"},
    })

    # Observability errors — TENANT-SCOPED (önceki sürüm tüm kiracıların toplamını dönüyordu, çok-kiracı sızıntısı)
    obs_errors = await db.observability_errors.count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": cutoff},
    })

    # observability_errors KPI'da görünüyordu ama total_failures'a dahil değildi → "Toplam Hata: 55" iken altta 265 göstererek tutarsız KPI üretiyordu.
    total = ari_fails + exely_fails + dlq_count + cp_fails + obs_errors

    return {
        "period_days": days,
        "total_failures": total,
        "breakdown": {
            "ari_hard_fails": ari_fails,
            "exely_sync_fails": exely_fails,
            "dlq_items": dlq_count,
            "control_plane_fails": cp_fails,
            "reconciliation_issues": recon_issues,
            "observability_errors": obs_errors,
        },
        "health_status": "healthy" if total == 0 else "warning" if total < 10 else "critical",
    }


@router.get("/recent")
async def get_recent_failures(
    limit: int = Query(default=50, ge=1, le=200),
    provider: str = Query(default="all"),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get recent wire failures with details."""
    tenant_id = current_user.tenant_id
    failures = []

    # ARI hard fail log entries
    if provider in ("all", "ari"):
        ari_docs = await db.ari_hard_fail_log.find(
            {"tenant_id": tenant_id},
            {"_id": 0},
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        for doc in ari_docs:
            failures.append({
                "id": doc.get("id", ""),
                "type": "ari_hard_fail",
                "provider": doc.get("provider", "unknown"),
                "message": doc.get("reason", doc.get("error", "")),
                "room_type": doc.get("room_type_code", ""),
                "timestamp": doc.get("timestamp", ""),
                "severity": "high",
                "resolved": False,
            })

    # Exely sync failures
    if provider in ("all", "exely"):
        exely_docs = await db.exely_sync_logs.find(
            {"tenant_id": tenant_id, "status": {"$in": ["failed", "error"]}},
            {"_id": 0},
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        for doc in exely_docs:
            failures.append({
                "id": doc.get("id", ""),
                "type": "exely_sync_fail",
                "provider": "exely",
                "message": doc.get("error", doc.get("sync_type", "")),
                "room_type": "",
                "timestamp": doc.get("timestamp", ""),
                "severity": "medium",
                "resolved": False,
            })

    # DLQ items
    if provider in ("all", "dlq"):
        dlq_docs = await db.connector_outbox.find(
            {"tenant_id": tenant_id, "status": {"$in": ["failed", "dead_letter"]}},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(limit)
        for doc in dlq_docs:
            failures.append({
                "id": doc.get("id", ""),
                "type": "dlq_item",
                "provider": doc.get("provider", "unknown"),
                "message": doc.get("error", doc.get("payload_type", "")),
                "room_type": doc.get("room_type_code", ""),
                "timestamp": doc.get("created_at", ""),
                "severity": "high",
                "resolved": doc.get("status") == "resolved",
            })

    # CP failures
    if provider in ("all", "control_plane"):
        cp_docs = await db.cp_failures.find(
            {"tenant_id": tenant_id},
            {"_id": 0},
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        for doc in cp_docs:
            failures.append({
                "id": doc.get("id", ""),
                "type": "cp_failure",
                "provider": doc.get("component", "control_plane"),
                "message": doc.get("message", doc.get("error", "")),
                "room_type": "",
                "timestamp": doc.get("timestamp", ""),
                "severity": doc.get("severity", "medium"),
                "resolved": doc.get("resolved", False),
            })

    # Sort all by timestamp desc
    failures.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {
        "failures": failures[:limit],
        "total": len(failures),
    }


@router.get("/trend")
@cached(ttl=120, key_prefix="wire_failures_trend")
async def get_failure_trend(
    days: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get daily failure trend for charts."""
    tenant_id = current_user.tenant_id
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    # Daily ARI failures
    daily = {}
    for i in range(days):
        day = (datetime.now(UTC) - timedelta(days=i)).strftime("%Y-%m-%d")
        daily[day] = {"date": day, "ari_fails": 0, "sync_fails": 0, "dlq": 0, "total": 0}

    # Count ARI hard fails per day
    ari_docs = await db.ari_hard_fail_log.find(
        {"tenant_id": tenant_id, "timestamp": {"$gte": cutoff}},
        {"_id": 0, "timestamp": 1},
    ).to_list(5000)
    for doc in ari_docs:
        ts = doc.get("timestamp", "")
        day = ts[:10] if len(ts) >= 10 else ""
        if day in daily:
            daily[day]["ari_fails"] += 1
            daily[day]["total"] += 1

    # Count Exely sync fails per day
    exely_docs = await db.exely_sync_logs.find(
        {"tenant_id": tenant_id, "status": {"$in": ["failed", "error"]}, "timestamp": {"$gte": cutoff}},
        {"_id": 0, "timestamp": 1},
    ).to_list(5000)
    for doc in exely_docs:
        ts = doc.get("timestamp", "")
        day = ts[:10] if len(ts) >= 10 else ""
        if day in daily:
            daily[day]["sync_fails"] += 1
            daily[day]["total"] += 1

    trend = sorted(daily.values(), key=lambda x: x["date"])
    return {"trend": trend, "period_days": days}
