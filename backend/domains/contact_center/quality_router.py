from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import db
from core.security import _is_super_admin, get_current_user
from domains.contact_center.quality_models import (
    CallEvaluationCreate,
    CallEvaluationResponse,
    ScorecardConfigCreate,
    ScorecardConfigResponse,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_module

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/contact-center", tags=["contact-center-quality"])


def _require_supervisor(current_user: User):
    """Enforce that only supervisor, admin, or super_admin can perform action."""
    if _is_super_admin(current_user):
        return
    role_val = getattr(current_user.role, "value", str(current_user.role))
    if role_val not in {"supervisor", "admin", "super_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yalnızca yönetici veya supervisor bu işlemi gerçekleştirebilir.")


@router.get("/quality/scorecards", response_model=list[ScorecardConfigResponse])
async def get_scorecards(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Retrieve all scorecard templates for the tenant."""
    cursor = db.contact_center_quality_scorecards.find({"tenant_id": current_user.tenant_id})
    docs = await cursor.to_list(length=100)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/quality/scorecards", response_model=ScorecardConfigResponse)
async def post_scorecard(
    payload: ScorecardConfigCreate,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Create or update a scorecard template (supervisor/admin only)."""
    _require_supervisor(current_user)
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC)

    # For simplicity, we upsert a single active scorecard template or save by name
    doc_id = str(uuid4())
    doc = {
        "id": doc_id,
        "tenant_id": tenant_id,
        "name": payload.name,
        "is_active": True,
        "sections": [s.model_dump() for s in payload.sections],
        "created_at": now,
        "updated_at": now,
    }
    # Deactivate existing ones if this is active
    await db.contact_center_quality_scorecards.update_many({"tenant_id": tenant_id}, {"$set": {"is_active": False, "updated_at": now}})
    await db.contact_center_quality_scorecards.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/calls/{call_id}/evaluations", response_model=CallEvaluationResponse)
async def post_call_evaluation(
    call_id: str,
    payload: CallEvaluationCreate,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Evaluate a call using a scorecard template (supervisor/admin only)."""
    _require_supervisor(current_user)
    tenant_id = current_user.tenant_id

    # 1. Fetch scorecard template
    scorecard = await db.contact_center_quality_scorecards.find_one({"id": payload.scorecard_id, "tenant_id": tenant_id})
    if not scorecard:
        raise HTTPException(status_code=404, detail="Değerlendirme şablonu bulunamadı.")

    # 2. Fetch call metadata
    call_doc = await db.contact_center_calls.find_one({"id": call_id, "tenant_id": tenant_id})
    if not call_doc:
        raise HTTPException(status_code=404, detail="Çağrı bulunamadı.")
    agent_id = call_doc.get("agent_id") or ""

    # 3. Calculate total score based on weights and points
    total_possible = 0.0
    total_earned = 0.0
    for section in scorecard.get("sections") or []:
        sec_weight = float(section.get("weight") or 1.0)
        for question in section.get("questions") or []:
            q_id = question.get("id")
            q_weight = float(question.get("weight") or 1.0)
            max_pts = float(question.get("max_points") or 10.0)

            points = float(payload.scores.get(q_id) or 0.0)
            # Clamp points
            points = max(0.0, min(points, max_pts))

            total_possible += max_pts * q_weight * sec_weight
            total_earned += points * q_weight * sec_weight

    total_score = (total_earned / total_possible * 100.0) if total_possible > 0 else 100.0

    # 4. Save evaluation
    eval_id = str(uuid4())
    doc = {
        "id": eval_id,
        "tenant_id": tenant_id,
        "call_id": call_id,
        "scorecard_id": payload.scorecard_id,
        "agent_id": agent_id,
        "evaluator_id": current_user.id,
        "scores": payload.scores,
        "total_score": round(total_score, 2),
        "comments": payload.comments,
        "coaching_notes": payload.coaching_notes,
        "created_at": datetime.now(UTC),
    }
    await db.contact_center_quality_evaluations.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/calls/{call_id}/evaluations", response_model=list[CallEvaluationResponse])
async def get_call_evaluations(
    call_id: str,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Retrieve all evaluations submitted for a call."""
    cursor = db.contact_center_quality_evaluations.find({"call_id": call_id, "tenant_id": current_user.tenant_id})
    docs = await cursor.to_list(length=100)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.get("/supervisor/quality-trends")
async def get_quality_trends(
    start_date: str | None = None,
    end_date: str | None = None,
    agent_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Retrieve quality trends for supervisor dashboard (supervisor/admin only)."""
    _require_supervisor(current_user)
    tenant_id = current_user.tenant_id

    query: dict = {"tenant_id": tenant_id}
    if agent_id:
        query["agent_id"] = agent_id

    date_filter = {}
    if start_date:
        try:
            date_filter["$gte"] = datetime.fromisoformat(start_date)
        except ValueError:
            pass
    if end_date:
        try:
            date_filter["$lte"] = datetime.fromisoformat(end_date)
        except ValueError:
            pass
    if date_filter:
        query["created_at"] = date_filter

    cursor = db.contact_center_quality_evaluations.find(query).sort("created_at", 1)
    evals = await cursor.to_list(length=1000)

    # Aggregate by date (YYYY-MM-DD) and agent
    trends = []
    daily_stats: dict = {}
    for ev in evals:
        dt = ev["created_at"].strftime("%Y-%m-%d")
        a_id = ev["agent_id"]
        key = (dt, a_id)
        if key not in daily_stats:
            daily_stats[key] = []
        daily_stats[key].append(ev["total_score"])

    # Resolve agent names
    agent_ids = list({k[1] for k in daily_stats.keys() if k[1]})
    agents_cursor = db.users.find({"id": {"$in": agent_ids}, "tenant_id": tenant_id})
    agents_map = {u["id"]: u.get("name") or u.get("username") async for u in agents_cursor}

    for (dt, a_id), scores in daily_stats.items():
        avg_score = sum(scores) / len(scores)
        trends.append(
            {
                "date": dt,
                "agent_id": a_id,
                "agent_name": agents_map.get(a_id) or f"Agent {a_id}",
                "average_score": round(avg_score, 2),
            }
        )

    return {"trends": sorted(trends, key=lambda x: x["date"])}
