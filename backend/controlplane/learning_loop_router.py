"""
Learning Loop API Router
=========================
Incident auto-classification, recurrence detection, RCA tracking,
never-again rules, and learning dashboard.
"""

from datetime import UTC
from modules.pms_core.role_permission_service import require_op  # v101 DW

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.learning_loop import (
    IncidentClassifier,
    LearningDashboard,
    RCAEngine,
    RecurrenceDetector,
)
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/ops/learning", tags=["Learning Loop"])

classifier = IncidentClassifier()
rca_engine = RCAEngine()
recurrence_detector = RecurrenceDetector()
learning_dashboard = LearningDashboard()


class CreateIncidentRequest(BaseModel):
    title: str
    description: str
    severity: str = "P2"
    affected_service: str = ""


class RCARequest(BaseModel):
    summary: str
    contributing_factors: list[str]
    five_whys: list[str] | None = None
    root_cause_type: str = "internal_bug"


class TrackFixRequest(BaseModel):
    fix_applied: str


class NeverAgainRuleRequest(BaseModel):
    rule_type: str = Field(..., description="circuit_breaker|alert_threshold|test_case|monitoring|process|config")
    description: str
    implementation: str
    verification_type: str = "test_exists"
    verification_detail: str = ""
    assigned_to: str = "backend_team"
    due_date: str | None = None


@router.post("/incidents")
async def create_incident(body: CreateIncidentRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Create incident with auto-classification."""
    import uuid
    from datetime import datetime

    from core.database import db

    tenant_id = current_user.tenant_id
    actor_id = current_user.id

    classification = classifier.classify(body.title, body.description)
    incident_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    incident = {
        "id": incident_id,
        "tenant_id": tenant_id,
        "title": body.title,
        "description": body.description,
        "severity": body.severity,
        "status": "open",
        "affected_service": body.affected_service,
        "classification": classification,
        "timeline": [
            {"action": "created", "actor": actor_id, "timestamp": now, "note": body.description}
        ],
        "metrics": {
            "detection_time_seconds": 0,
            "acknowledgement_time_seconds": None,
            "mitigation_time_seconds": None,
            "resolution_time_seconds": None,
            "total_duration_seconds": 0,
        },
        "recurrence": {
            "is_recurrence": False,
            "previous_incident_ids": [],
            "recurrence_count": 0,
            "pattern_signature": None,
        },
        "never_again_rules": [],
        "root_cause_analysis": None,
        "created_at": now,
        "updated_at": now,
        "created_by": actor_id,
    }

    await db.incidents.insert_one(incident)

    # Auto-detect recurrence
    recurrence = await recurrence_detector.detect_recurrence(
        tenant_id, incident_id,
        classification["category"],
        classification["subcategory"],
        body.affected_service,
    )

    return {
        "incident_id": incident_id,
        "classification": classification,
        "recurrence": recurrence,
    }


@router.put("/incidents/{incident_id}/rca")
async def add_rca(incident_id: str, body: RCARequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    try:
        result = await rca_engine.create_rca(
            current_user.tenant_id, incident_id,
            body.summary, body.contributing_factors,
            body.five_whys, body.root_cause_type,
            current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/incidents/{incident_id}/fix")
async def track_fix(incident_id: str, body: TrackFixRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    try:
        result = await rca_engine.track_fix(
            current_user.tenant_id, incident_id,
            body.fix_applied, current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/incidents/{incident_id}/never-again")
async def add_never_again_rule(incident_id: str, body: NeverAgainRuleRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    try:
        result = await rca_engine.create_never_again_rule(
            current_user.tenant_id, incident_id,
            body.rule_type, body.description,
            body.implementation, body.verification_type,
            body.verification_detail, body.assigned_to,
            body.due_date,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/incidents/{incident_id}/recurrence")
async def check_recurrence(incident_id: str, current_user: User = Depends(get_current_user)):
    from core.database import db
    incident = await db.incidents.find_one(
        {"id": incident_id, "tenant_id": current_user.tenant_id},
        {"_id": 0, "classification": 1, "affected_service": 1},
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    cls = incident.get("classification", {})
    return await recurrence_detector.detect_recurrence(
        current_user.tenant_id, incident_id,
        cls.get("category", "unknown"),
        cls.get("subcategory", "unknown"),
        incident.get("affected_service", ""),
    )


@router.post("/incidents/{incident_id}/verify-prevention")
async def verify_prevention(incident_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    try:
        return await rca_engine.verify_prevention(current_user.tenant_id, incident_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/dashboard")
async def get_learning_dashboard(current_user: User = Depends(get_current_user)):
    return await learning_dashboard.get_metrics(current_user.tenant_id)
