"""
Operator Incident Panel — Backend API
======================================

Endpoints for managing operational incidents:
- List incidents (reconciliation cases, hard fails, drift alerts)
- Update incident status (retry, review, resolve, suppress)
- Audit trail per incident
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from domains.channel_manager.ari.models import COLL_ARI_CHANGE_SETS
from domains.channel_manager.data_model import (
    COLL_RECONCILIATION_CASES,
    COLL_RESERVATION_LINEAGE,
)
from domains.channel_manager.reconciliation_truth import (
    can_auto_heal,
    get_resolution_for_drift,
)
from models.schemas import User

logger = logging.getLogger("incident.panel")
router = APIRouter(prefix="/api/ops/incidents", tags=["Operator Incident Panel"])

_NO_ID = {"_id": 0}

COLL_INCIDENT_AUDIT = "incident_audit_trail"


# ── Request Models ────────────────────────────────────────────

class IncidentActionRequest(BaseModel):
    action: str  # retry | review | resolve | suppress
    note: Optional[str] = None


# ── 1. LIST INCIDENTS ─────────────────────────────────────────

@router.get("/list")
async def list_incidents(
    status: Optional[str] = Query(default=None, description="open|investigating|resolved|suppressed"),
    severity: Optional[str] = Query(default=None, description="critical|high|medium|low"),
    provider: Optional[str] = Query(default=None),
    issue_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """List operational incidents with filters."""
    tenant_id = current_user.tenant_id
    query = {"tenant_id": tenant_id}

    if status:
        query["status"] = status
    if severity:
        query["severity"] = severity
    if provider:
        query["provider"] = provider
    if issue_type:
        query["$or"] = [{"drift_type": issue_type}, {"case_type": issue_type}]

    incidents = await db[COLL_RECONCILIATION_CASES].find(
        query, _NO_ID,
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    total = await db[COLL_RECONCILIATION_CASES].count_documents(query)

    # Enrich with resolution recommendations
    enriched = []
    for inc in incidents:
        drift_type = inc.get("drift_type") or inc.get("case_type", "")
        rule = get_resolution_for_drift(drift_type)
        enriched.append({
            **inc,
            "issue_type": drift_type,
            "recommended_action": rule.resolution.value if rule else "manual_review",
            "can_auto_heal": can_auto_heal(drift_type),
            "gold_source": rule.gold_source.value if rule else "",
            "auto_heal_description": rule.auto_heal_action if rule else "",
        })

    return {
        "incidents": enriched,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


# ── 2. INCIDENT DETAIL ───────────────────────────────────────

@router.get("/detail/{incident_id}")
async def get_incident_detail(
    incident_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get full incident details with related data."""
    tenant_id = current_user.tenant_id

    incident = await db[COLL_RECONCILIATION_CASES].find_one(
        {"tenant_id": tenant_id, "id": incident_id},
        _NO_ID,
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Get audit trail
    audit = await db[COLL_INCIDENT_AUDIT].find(
        {"incident_id": incident_id},
        _NO_ID,
    ).sort("timestamp", -1).to_list(50)

    # Get related reservation lineage
    ext_res_id = incident.get("external_reservation_id")
    lineage = None
    if ext_res_id:
        lineage = await db[COLL_RESERVATION_LINEAGE].find_one(
            {"tenant_id": tenant_id, "external_reservation_id": ext_res_id},
            _NO_ID,
        )

    # Get related ARI change sets (if ARI-related)
    related_ari = []
    if incident.get("drift_type") in ("payload_mismatch", "stale_remotely"):
        room = incident.get("room_type_code")
        prov = incident.get("provider")
        if room and prov:
            related_ari = await db[COLL_ARI_CHANGE_SETS].find(
                {
                    "tenant_id": tenant_id,
                    "provider": prov,
                    "room_type_code": room,
                    "status": {"$in": ["failed_retryable", "manual_review"]},
                },
                _NO_ID,
            ).sort("updated_at", -1).limit(10).to_list(10)

    drift_type = incident.get("drift_type", "")
    rule = get_resolution_for_drift(drift_type)

    return {
        "incident": {
            **incident,
            "recommended_action": rule.resolution.value,
            "can_auto_heal": can_auto_heal(drift_type),
            "gold_source": rule.gold_source.value,
            "auto_heal_description": rule.auto_heal_action,
        },
        "audit_trail": audit,
        "related_lineage": lineage,
        "related_ari_issues": related_ari,
    }


# ── 3. UPDATE INCIDENT STATUS ────────────────────────────────

@router.post("/action/{incident_id}")
async def incident_action(
    incident_id: str,
    request: IncidentActionRequest,
    current_user: User = Depends(get_current_user),
):
    """Apply an action to an incident: retry, review, resolve, suppress."""
    tenant_id = current_user.tenant_id
    action = request.action
    valid_actions = {"retry", "review", "resolve", "suppress"}

    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}")

    incident = await db[COLL_RECONCILIATION_CASES].find_one(
        {"tenant_id": tenant_id, "id": incident_id},
        _NO_ID,
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    now = datetime.now(timezone.utc).isoformat()
    actor = getattr(current_user, "email", "system")

    # Map action to new status
    status_map = {
        "retry": "investigating",
        "review": "investigating",
        "resolve": "resolved",
        "suppress": "suppressed",
    }
    new_status = status_map[action]

    # Update incident
    update = {
        "$set": {
            "status": new_status,
            "updated_at": now,
            "last_action": action,
            "last_action_by": actor,
        }
    }
    if action == "resolve":
        update["$set"]["resolved_at"] = now
        update["$set"]["resolved_by"] = actor

    await db[COLL_RECONCILIATION_CASES].update_one(
        {"tenant_id": tenant_id, "id": incident_id},
        update,
    )

    # Create audit trail entry
    await db[COLL_INCIDENT_AUDIT].insert_one({
        "incident_id": incident_id,
        "tenant_id": tenant_id,
        "action": action,
        "actor": actor,
        "note": request.note or "",
        "previous_status": incident.get("status"),
        "new_status": new_status,
        "timestamp": now,
    })

    return {
        "success": True,
        "incident_id": incident_id,
        "action": action,
        "new_status": new_status,
    }


# ── 4. INCIDENT SUMMARY STATS ────────────────────────────────

@router.get("/summary")
async def incident_summary(
    current_user: User = Depends(get_current_user),
):
    """Dashboard-level incident summary."""
    tenant_id = current_user.tenant_id

    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {
            "_id": {"status": "$status", "severity": {"$ifNull": ["$severity", "medium"]}},
            "count": {"$sum": 1},
        }},
    ]

    by_status = {}
    by_severity = {}
    total = 0

    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(pipeline):
        status = doc["_id"]["status"]
        severity = doc["_id"]["severity"]
        count = doc["count"]
        total += count
        by_status[status] = by_status.get(status, 0) + count
        by_severity[severity] = by_severity.get(severity, 0) + count

    # Type breakdown
    type_pipeline = [
        {"$match": {"tenant_id": tenant_id, "status": {"$in": ["open", "investigating"]}}},
        {"$group": {
            "_id": {"$ifNull": ["$drift_type", {"$ifNull": ["$case_type", "unknown"]}]},
            "count": {"$sum": 1},
        }},
    ]
    by_type = {}
    async for doc in db[COLL_RECONCILIATION_CASES].aggregate(type_pipeline):
        if doc["_id"]:
            by_type[doc["_id"]] = doc["count"]

    # Failed ARI pushes (manual review)
    ari_dead_letters = await db[COLL_ARI_CHANGE_SETS].count_documents(
        {"tenant_id": tenant_id, "status": "manual_review"},
    )

    return {
        "total_incidents": total,
        "by_status": by_status,
        "by_severity": by_severity,
        "by_type": by_type,
        "ari_dead_letters": ari_dead_letters,
        "open_count": by_status.get("open", 0) + by_status.get("investigating", 0),
        "resolved_count": by_status.get("resolved", 0),
    }
