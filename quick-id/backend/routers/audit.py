"""Audit log endpoints: per-guest, recent (auth-filtered), and admin-only auth audit."""
from fastapi import APIRouter, Depends, Query

from auth import require_admin, require_auth
from db import audit_col, users_col
from helpers import serialize_doc

router = APIRouter()


@router.get("/api/guests/{guest_id}/audit")
async def get_guest_audit(guest_id: str, user=Depends(require_auth)):
    cursor = audit_col.find({"guest_id": guest_id}).sort("created_at", -1)
    logs = [serialize_doc(doc) async for doc in cursor]
    return {"audit_logs": logs, "total": len(logs)}


@router.get("/api/audit/recent")
async def get_recent_audit(limit: int = Query(50, ge=1, le=200), user=Depends(require_auth)):
    # v49 R1/R2: cannot trust JWT 'role' (stale on demote) — re-fetch from DB.
    db_user = await users_col.find_one({"email": user.get("email")}, {"role": 1, "is_active": 1})
    is_admin_now = bool(db_user and db_user.get("role") == "admin" and db_user.get("is_active", True))
    q = {} if is_admin_now else {"category": {"$ne": "auth"}}
    cursor = audit_col.find(q).sort("created_at", -1).limit(limit)
    logs = [serialize_doc(doc) async for doc in cursor]
    return {"audit_logs": logs, "total": len(logs)}


@router.get("/api/audit/auth")
async def get_auth_audit(
    limit: int = Query(100, ge=1, le=500),
    action: str = Query(None),
    actor_id: str = Query(None),
    target_id: str = Query(None),
    outcome: str = Query(None),
    user=Depends(require_admin),
):
    q = {"category": "auth"}
    if action: q["action"] = action
    if actor_id: q["actor_id"] = actor_id
    if target_id: q["target_id"] = target_id
    if outcome: q["outcome"] = outcome
    cursor = audit_col.find(q).sort("created_at", -1).limit(limit)
    logs = [serialize_doc(doc) async for doc in cursor]
    return {"audit_logs": logs, "total": len(logs), "filter": q}
