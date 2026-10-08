"""Quality management: standards, audits, findings and CAPA follow-up."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/quality", tags=["quality-management"])

KINDS = ("standard", "audit", "finding", "capa")
STATUSES = ("draft", "open", "in_progress", "pending_verification", "closed", "cancelled")
SEVERITIES = ("low", "medium", "high", "critical")
TRANSITIONS = {
    "draft": {"open", "cancelled"},
    "open": {"in_progress", "cancelled"},
    "in_progress": {"pending_verification", "cancelled"},
    "pending_verification": {"in_progress", "closed"},
    "closed": {"open"},
    "cancelled": {"open"},
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _query(tenant_id: str, **extra: object) -> dict:
    return {"tenant_id": tenant_id, "_kind": {"$in": [f"quality_{kind}" for kind in KINDS]}, "deleted_at": {"$exists": False}, **extra}


class ChecklistItem(BaseModel):
    label: str = Field(min_length=2, max_length=240)
    required: bool = True
    result: Literal["pending", "pass", "fail", "not_applicable"] = "pending"
    note: str | None = Field(default=None, max_length=1000)


class QualityRecordInput(BaseModel):
    kind: Literal["standard", "audit", "finding", "capa"]
    title: str = Field(min_length=3, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    department: str = Field(min_length=2, max_length=100)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    owner_id: str | None = Field(default=None, max_length=120)
    due_at: str | None = None
    source: str | None = Field(default=None, max_length=120)
    source_record_id: str | None = Field(default=None, max_length=120)
    standard_id: str | None = Field(default=None, max_length=120)
    audit_id: str | None = Field(default=None, max_length=120)
    finding_id: str | None = Field(default=None, max_length=120)
    root_cause: str | None = Field(default=None, max_length=4000)
    corrective_action: str | None = Field(default=None, max_length=4000)
    preventive_action: str | None = Field(default=None, max_length=4000)
    verification_note: str | None = Field(default=None, max_length=4000)
    checklist: list[ChecklistItem] = Field(default_factory=list, max_length=100)
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Geçersiz hedef tarihi") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()


class TransitionInput(BaseModel):
    status: Literal["draft", "open", "in_progress", "pending_verification", "closed", "cancelled"]
    note: str | None = Field(default=None, max_length=2000)


def validate_transition(current: str, target: str, record: dict) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=409, detail=f"'{current}' durumundan '{target}' durumuna geçilemez")
    if target == "closed":
        if record.get("_kind") == "quality_capa" and not record.get("verification_note"):
            raise HTTPException(status_code=422, detail="CAPA kapatılmadan önce doğrulama notu zorunludur")
        failed_required = [item for item in record.get("checklist", []) if item.get("required") and item.get("result") in {"pending", "fail"}]
        if failed_required:
            raise HTTPException(status_code=422, detail="Zorunlu kontrol maddeleri tamamlanmadan kayıt kapatılamaz")


@router.get("/dashboard")
async def quality_dashboard(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_quality")),
):
    rows = await db.tasks.find(_query(current_user.tenant_id), {"_id": 0}).sort("created_at", -1).to_list(2000)
    now = _now()
    summary = {"total": len(rows), "open": 0, "overdue": 0, "critical": 0, "closed": 0, "by_kind": dict.fromkeys(KINDS, 0), "by_department": {}}
    for row in rows:
        status = row.get("status", "open")
        kind = str(row.get("_kind", "")).removeprefix("quality_")
        if kind in summary["by_kind"]:
            summary["by_kind"][kind] += 1
        department = row.get("department") or "Diğer"
        summary["by_department"][department] = summary["by_department"].get(department, 0) + 1
        if status == "closed":
            summary["closed"] += 1
        elif status != "cancelled":
            summary["open"] += 1
            if row.get("due_at") and row["due_at"] < now:
                summary["overdue"] += 1
        if row.get("severity") == "critical" and status not in {"closed", "cancelled"}:
            summary["critical"] += 1
    summary["closure_rate"] = round(summary["closed"] / summary["total"] * 100, 1) if summary["total"] else 0
    return {"summary": summary, "recent": rows[:10]}


@router.get("/records")
async def list_quality_records(
    kind: Literal["standard", "audit", "finding", "capa"] | None = None,
    status: Literal["draft", "open", "in_progress", "pending_verification", "closed", "cancelled"] | None = None,
    department: str | None = None,
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_quality")),
):
    query = _query(current_user.tenant_id)
    if kind:
        query["_kind"] = f"quality_{kind}"
    if status:
        query["status"] = status
    if department:
        query["department"] = department
    rows = await db.tasks.find(query, {"_id": 0}).sort("updated_at", -1).limit(limit).to_list(limit)
    return {"records": rows, "total": len(rows)}


@router.post("/records", status_code=201)
async def create_quality_record(
    payload: QualityRecordInput,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_quality")),
):
    now = _now()
    record = {
        **payload.model_dump(),
        "_kind": f"quality_{payload.kind}",
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "status": "draft" if payload.kind == "standard" else "open",
        "created_at": now,
        "updated_at": now,
        "created_by": current_user.id,
        "history": [{"at": now, "by": current_user.id, "action": "created"}],
    }
    record.pop("kind", None)
    await db.tasks.insert_one(record)
    await create_audit_log(current_user.tenant_id, current_user, "quality_record_created", "quality_record", record["id"], {"kind": payload.kind})
    return {"record": {k: v for k, v in record.items() if k != "_id"}}


@router.put("/records/{record_id}")
async def update_quality_record(
    record_id: str,
    payload: QualityRecordInput,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_quality")),
):
    existing = await db.tasks.find_one(_query(current_user.tenant_id, id=record_id), {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kalite kaydı bulunamadı")
    if existing.get("_kind") != f"quality_{payload.kind}":
        raise HTTPException(status_code=409, detail="Kayıt türü değiştirilemez")
    update = payload.model_dump()
    update.pop("kind", None)
    update.update({"updated_at": _now(), "updated_by": current_user.id})
    await db.tasks.update_one(_query(current_user.tenant_id, id=record_id), {"$set": update})
    await create_audit_log(current_user.tenant_id, current_user, "quality_record_updated", "quality_record", record_id)
    return {"success": True, "record_id": record_id}


@router.post("/records/{record_id}/transition")
async def transition_quality_record(
    record_id: str,
    payload: TransitionInput,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_quality")),
):
    record = await db.tasks.find_one(_query(current_user.tenant_id, id=record_id), {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Kalite kaydı bulunamadı")
    current = record.get("status", "open")
    validate_transition(current, payload.status, record)
    now = _now()
    event = {"at": now, "by": current_user.id, "action": "status_changed", "from": current, "to": payload.status, "note": payload.note}
    await db.tasks.update_one(_query(current_user.tenant_id, id=record_id), {"$set": {"status": payload.status, "updated_at": now, "updated_by": current_user.id}, "$push": {"history": event}})
    await create_audit_log(current_user.tenant_id, current_user, "quality_status_changed", "quality_record", record_id, {"from": current, "to": payload.status})
    return {"success": True, "record_id": record_id, "status": payload.status}


@router.delete("/records/{record_id}")
async def archive_quality_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_quality")),
):
    now = _now()
    result = await db.tasks.update_one(_query(current_user.tenant_id, id=record_id), {"$set": {"deleted_at": now, "deleted_by": current_user.id}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kalite kaydı bulunamadı")
    await create_audit_log(current_user.tenant_id, current_user, "quality_record_archived", "quality_record", record_id)
    return {"success": True, "record_id": record_id}


@router.get("/feedback")
async def quality_feedback(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_quality")),
):
    rows = await db.feedback_entries.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("responded_at", -1).limit(limit).to_list(limit)
    ratings = [float(row["rating"]) for row in rows if row.get("rating") is not None]
    detractors = sum(1 for row in rows if row.get("nps_eligible") and int(row.get("nps_score", 0)) <= 6)
    return {
        "entries": rows,
        "summary": {
            "total": len(rows),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "detractors": detractors,
            "unresolved": sum(1 for row in rows if row.get("resolution_status") not in {"resolved", "closed"}),
        },
    }
