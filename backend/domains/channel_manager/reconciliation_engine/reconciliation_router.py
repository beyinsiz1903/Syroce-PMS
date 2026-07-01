"""
Cross-Provider Reconciliation — API Router
============================================

Operational APIs for the reconciliation engine.

Endpoints:
  GET  /api/channel-manager/reconciliation/cases         — List cases (filterable)
  GET  /api/channel-manager/reconciliation/cases/{id}    — Get case detail
  POST /api/channel-manager/reconciliation/{id}/resolve  — Resolve a case
  POST /api/channel-manager/reconciliation/{id}/ignore   — Ignore a case
  POST /api/channel-manager/reconciliation/{id}/acknowledge — Acknowledge a case
  POST /api/channel-manager/reconciliation/run           — Trigger manual run
  POST /api/channel-manager/reconciliation/run-with-snapshots — Run with test snapshots
  GET  /api/channel-manager/reconciliation/dashboard     — Dashboard summary data
  GET  /api/channel-manager/reconciliation/metrics       — Reconciliation metrics
  GET  /api/channel-manager/reconciliation/worker/status — Worker status
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    COLL_RECONCILIATION_CASES,
    CaseStatus,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

from .reconciliation_worker import (
    get_reconciliation_worker_state,
    reconciliation_run_once,
    reconciliation_run_with_snapshots,
)

logger = logging.getLogger("reconciliation.router")

_NO_ID = {"_id": 0}

router = APIRouter(
    prefix="/api/channel-manager/reconciliation",
    tags=["Cross-Provider Reconciliation"],
)


# ── Request Models ────────────────────────────────────────────────────


class ResolveCaseRequest(BaseModel):
    resolution: str


class IgnoreCaseRequest(BaseModel):
    reason: str = ""


class AcknowledgeCaseRequest(BaseModel):
    note: str = ""


class RunWithSnapshotsRequest(BaseModel):
    provider: str
    property_id: str = "prop-001"
    snapshots: list[dict[str, Any]] = Field(default_factory=list)


# ── List Cases ────────────────────────────────────────────────────────


@router.get("/cases")
async def list_reconciliation_cases(
    property_id: str | None = None,
    provider: str | None = None,
    status: str | None = Query(None),
    case_type: str | None = None,
    severity: str | None = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    """List reconciliation cases with filters."""
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if property_id:
        q["property_id"] = property_id
    if provider:
        q["provider"] = provider
    if status:
        q["status"] = status
    if case_type:
        q["case_type"] = case_type
    if severity:
        q["severity"] = severity

    cases = (
        await db[COLL_RECONCILIATION_CASES]
        .find(
            q,
            _NO_ID,
        )
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )

    return {"cases": cases, "count": len(cases)}


# ── Get Case Detail ───────────────────────────────────────────────────


@router.get("/cases/{case_id}")
async def get_case_detail(
    case_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed information about a specific case."""
    case = await repo.get_reconciliation_case(current_user.tenant_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


# ── Resolve Case ──────────────────────────────────────────────────────


@router.post("/cases/{case_id}/resolve")
async def resolve_case(
    case_id: str,
    req: ResolveCaseRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Resolve a reconciliation case."""
    case = await repo.get_reconciliation_case(current_user.tenant_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.get("status") in ["resolved", "ignored", "dismissed"]:
        raise HTTPException(status_code=400, detail="Case already closed")

    await repo.update_reconciliation_case(
        case_id,
        {
            "status": CaseStatus.RESOLVED.value,
            "resolution": req.resolution,
            "resolved_by": current_user.id,
            "resolved_at": datetime.now(UTC).isoformat(),
        },
    )
    return {"message": "Case resolved", "case_id": case_id}


# ── Ignore Case ───────────────────────────────────────────────────────


@router.post("/cases/{case_id}/ignore")
async def ignore_case(
    case_id: str,
    req: IgnoreCaseRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Ignore a reconciliation case."""
    case = await repo.get_reconciliation_case(current_user.tenant_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.get("status") in ["resolved", "ignored", "dismissed"]:
        raise HTTPException(status_code=400, detail="Case already closed")

    await repo.update_reconciliation_case(
        case_id,
        {
            "status": CaseStatus.IGNORED.value,
            "dismiss_reason": req.reason,
            "resolved_by": current_user.id,
            "resolved_at": datetime.now(UTC).isoformat(),
        },
    )
    return {"message": "Case ignored", "case_id": case_id}


# ── Acknowledge Case ─────────────────────────────────────────────────


@router.post("/cases/{case_id}/acknowledge")
async def acknowledge_case(
    case_id: str,
    req: AcknowledgeCaseRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Acknowledge a case (mark as under review)."""
    case = await repo.get_reconciliation_case(current_user.tenant_id, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await repo.update_reconciliation_case(
        case_id,
        {
            "status": CaseStatus.ACKNOWLEDGED.value,
            "details": {
                **(case.get("details") or {}),
                "acknowledged_by": current_user.id,
                "acknowledged_at": datetime.now(UTC).isoformat(),
                "acknowledge_note": req.note,
            },
        },
    )
    return {"message": "Case acknowledged", "case_id": case_id}


# ── Trigger Manual Run ────────────────────────────────────────────────


@router.post("/run")
async def trigger_reconciliation(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Trigger a manual reconciliation run across all providers."""
    result = await reconciliation_run_once()
    return {"message": "Reconciliation completed", "result": result}


# ── Run With Snapshots (Test) ─────────────────────────────────────────


@router.post("/run-with-snapshots")
async def run_with_snapshots(
    req: RunWithSnapshotsRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """
    Run reconciliation with explicitly provided provider snapshots.
    Useful for testing and manual verification.
    """
    result = await reconciliation_run_with_snapshots(
        tenant_id=current_user.tenant_id,
        property_id=req.property_id,
        provider=req.provider,
        provider_snapshots=req.snapshots,
    )
    return {"message": "Reconciliation with snapshots completed", "result": result}


# ── Dashboard Data ────────────────────────────────────────────────────


@router.get("/dashboard")
async def get_dashboard_data(
    provider: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get comprehensive dashboard data for reconciliation."""
    tenant_id = current_user.tenant_id

    # Open cases count
    open_q: dict[str, Any] = {
        "tenant_id": tenant_id,
        "status": {"$in": ["open", "acknowledged"]},
    }
    if provider:
        open_q["provider"] = provider

    # Severity breakdown
    severity_pipeline = [
        {"$match": open_q},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    severity_counts: dict[str, int] = {}
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(severity_pipeline):
        severity_counts[doc["_id"]] = doc["count"]

    # Provider breakdown
    provider_pipeline = [
        {"$match": open_q},
        {"$group": {"_id": "$provider", "count": {"$sum": 1}}},
    ]
    provider_breakdown: dict[str, int] = {}
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(provider_pipeline):
        provider_breakdown[doc["_id"]] = doc["count"]

    # Case type breakdown
    type_pipeline = [
        {"$match": open_q},
        {"$group": {"_id": "$case_type", "count": {"$sum": 1}}},
    ]
    type_breakdown: dict[str, int] = {}
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(type_pipeline):
        type_breakdown[doc["_id"]] = doc["count"]

    # Recent cases (last 20)
    recent_cases = (
        await db[COLL_RECONCILIATION_CASES]
        .find(
            {"tenant_id": tenant_id} | ({"provider": provider} if provider else {}),
            _NO_ID,
        )
        .sort("created_at", -1)
        .limit(20)
        .to_list(20)
    )

    total_open = sum(severity_counts.values())

    return {
        "open_cases": total_open,
        "severity_counts": severity_counts,
        "provider_breakdown": provider_breakdown,
        "type_breakdown": type_breakdown,
        "recent_cases": recent_cases,
        "worker": get_reconciliation_worker_state(),
    }


# ── Metrics ───────────────────────────────────────────────────────────


@router.get("/metrics")
async def get_reconciliation_metrics(
    current_user: User = Depends(get_current_user),
):
    """Get reconciliation metrics for observability."""
    tenant_id = current_user.tenant_id

    # Total cases by status
    status_pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    by_status: dict[str, int] = {}
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(status_pipeline):
        by_status[doc["_id"]] = doc["count"]

    # Specific mismatch counts
    mismatch_pipeline = [
        {"$match": {"tenant_id": tenant_id, "status": {"$in": ["open", "acknowledged"]}}},
        {"$group": {"_id": "$case_type", "count": {"$sum": 1}}},
    ]
    mismatch_counts: dict[str, int] = {}
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(mismatch_pipeline):
        mismatch_counts[doc["_id"]] = doc["count"]

    worker = get_reconciliation_worker_state()

    return {
        "cases_open": by_status.get("open", 0) + by_status.get("acknowledged", 0),
        "cases_resolved": by_status.get("resolved", 0),
        "cases_ignored": by_status.get("ignored", 0) + by_status.get("dismissed", 0),
        "cases_total": sum(by_status.values()),
        "missing_reservations": mismatch_counts.get("missing_reservation", 0),
        "ghost_reservations": mismatch_counts.get("ghost_reservation", 0),
        "status_conflicts": mismatch_counts.get("status_conflict", 0),
        "amount_mismatches": mismatch_counts.get("amount_mismatch", 0),
        "date_conflicts": mismatch_counts.get("date_conflict", 0),
        "duplicate_reservations": mismatch_counts.get("duplicate_reservation", 0),
        "worker": worker,
    }


# ── Worker Status ─────────────────────────────────────────────────────


@router.get("/worker/status")
async def get_worker_status(
    current_user: User = Depends(get_current_user),
):
    """Get current reconciliation worker status."""
    return {"worker": get_reconciliation_worker_state()}
