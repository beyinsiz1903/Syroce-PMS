"""Physical Security Management Router.

Handles CCTV configurations, searchable access logs, and global lock-down protocols.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.audit import log_audit_event
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/physical-security", tags=["physical-security"])


class CameraRegisterIn(BaseModel):
    camera_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=150)
    room_number: str = Field(..., min_length=1, max_length=50)
    stream_url: str = Field(..., min_length=1, max_length=1000)


@router.post("/cctv/cameras")
async def register_cctv_camera(
    payload: CameraRegisterIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_security")),
):
    db = get_system_db()
    tenant_id = current_user.tenant_id

    # Check for duplicate camera_id
    existing = await db.cctv_cameras.find_one({"tenant_id": tenant_id, "camera_id": payload.camera_id})
    if existing:
        raise HTTPException(status_code=400, detail="Bu kamera ID zaten kayıtlı")

    camera = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "camera_id": payload.camera_id,
        "name": payload.name,
        "room_number": payload.room_number,
        "stream_url": payload.stream_url,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.cctv_cameras.insert_one(camera)

    await log_audit_event(
        tenant_id=tenant_id,
        user_id=current_user.id,
        action="cctv.camera.register",
        entity_type="cctv_camera",
        entity_id=camera["id"],
        details=f"CCTV camera registered: {payload.name} (Room: {payload.room_number})",
        severity="info",
    )
    return {"success": True, "camera_id": camera["id"]}


@router.get("/cctv/cameras")
async def list_cctv_cameras(
    room_number: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_security")),
):
    db = get_system_db()
    tenant_id = current_user.tenant_id

    q = {"tenant_id": tenant_id}
    if room_number:
        q["room_number"] = room_number

    cameras = await db.cctv_cameras.find(q, {"_id": 0}).to_list(1000)
    return {"cameras": cameras}


@router.get("/access-logs")
async def get_physical_access_logs(
    room_number: str | None = None,
    booking_id: str | None = None,
    guest_id: str | None = None,
    access_decision: Literal["granted", "denied"] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_security")),
):
    db = get_system_db()
    tenant_id = current_user.tenant_id

    q: dict[str, Any] = {"tenant_id": tenant_id}

    if room_number:
        q["room_number"] = room_number
    if booking_id:
        q["booking_id"] = booking_id
    if guest_id:
        q["guest_id"] = guest_id
    if access_decision:
        q["access_decision"] = access_decision

    if start_date or end_date:
        ts_filter = {}
        if start_date:
            ts_filter["$gte"] = start_date
        if end_date:
            ts_filter["$lte"] = end_date
        q["timestamp"] = ts_filter

    logs = await db.physical_access_logs.find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return {"logs": logs}


@router.post("/lockdown")
async def activate_lockdown(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_security")),
):
    """Enacts global lockdown protocol (fail-closed). Revokes all active keys immediately."""
    db = get_system_db()
    tenant_id = current_user.tenant_id

    # 1. Update lockdown state to active
    await db.lockdown_state.update_one({"tenant_id": tenant_id}, {"$set": {"status": "active", "activated_at": datetime.now(UTC).isoformat(), "activated_by": current_user.id}}, upsert=True)

    # 2. Revoke all active digital keys immediately (fail-closed)
    res = await db.digital_keys.update_many({"tenant_id": tenant_id, "status": "active"}, {"$set": {"status": "revoked", "revoked_at": datetime.now(UTC).isoformat(), "revocation_reason": "lockdown"}})

    await log_audit_event(
        tenant_id=tenant_id,
        user_id=current_user.id,
        action="lockdown.activate",
        entity_type="system",
        entity_id="global",
        details=f"GLOBAL LOCKDOWN ACTIVATED. Revoked {res.modified_count} active digital keys.",
        severity="critical",
    )

    return {"success": True, "message": "Global lockdown activated. All keys revoked, doors locked.", "keys_revoked_count": res.modified_count}


@router.post("/lockdown/release")
async def release_lockdown(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_security")),
):
    """Releases global lockdown state."""
    db = get_system_db()
    tenant_id = current_user.tenant_id

    res = await db.lockdown_state.delete_one({"tenant_id": tenant_id})
    if res.deleted_count == 0:
        return {"success": True, "message": "Sistemde aktif lockdown bulunamadı"}

    await log_audit_event(tenant_id=tenant_id, user_id=current_user.id, action="lockdown.release", entity_type="system", entity_id="global", details="GLOBAL LOCKDOWN RELEASED.", severity="warning")

    return {"success": True, "message": "Global lockdown released."}
