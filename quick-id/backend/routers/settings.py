"""Settings & KVKK endpoints: get/patch kvkk, cleanup, anonymize-guest."""
from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_admin, require_auth
from db import db
from helpers import create_audit_log, create_auth_audit_log
from kvkk import anonymize_guest, get_settings, run_data_cleanup, update_settings
from rate_limit import limiter
from schemas import SettingsUpdate

router = APIRouter()


@router.get("/api/settings/kvkk")
async def get_kvkk_settings(user=Depends(require_auth)):
    settings = await get_settings(db)
    return {"settings": settings}


@router.patch("/api/settings/kvkk")
@limiter.limit("20/minute")
async def update_kvkk_settings(request: Request, req: SettingsUpdate, user=Depends(require_admin)):
    # v109 Bug DAJ round-2: forensic-floor enforcement (audit≥365d, scans≥30d).
    from kvkk import RetentionFloorViolation
    actor_id = user.get("sub")
    actor_email = user.get("email")
    ip = request.client.host if request and request.client else None
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        settings = await update_settings(db, updates)
    except RetentionFloorViolation as exc:
        await create_auth_audit_log("kvkk_settings_blocked",
            actor_id=actor_id, actor_email=actor_email,
            outcome="blocked", reason=str(exc),
            metadata={"attempted_updates": updates}, ip_address=ip)
        raise HTTPException(status_code=400, detail=str(exc))
    await create_auth_audit_log("kvkk_settings_updated",
        actor_id=actor_id, actor_email=actor_email,
        outcome="success",
        metadata={"updates": updates}, ip_address=ip)
    return {"success": True, "settings": settings}


@router.post("/api/settings/cleanup")
@limiter.limit("5/minute")
async def trigger_cleanup(request: Request, user=Depends(require_admin)):
    actor_id = user.get("sub")
    actor_email = user.get("email")
    ip = request.client.host if request and request.client else None
    results = await run_data_cleanup(db)
    await create_auth_audit_log("data_cleanup_triggered",
        actor_id=actor_id, actor_email=actor_email,
        outcome="success", metadata={"results": results}, ip_address=ip)
    return {"success": True, "results": results}


@router.post("/api/guests/{guest_id}/anonymize")
async def anonymize_guest_endpoint(guest_id: str, user=Depends(require_admin)):
    success = await anonymize_guest(db, guest_id)
    if not success:
        raise HTTPException(status_code=404, detail="Misafir bulunamadı")
    await create_audit_log(guest_id, "anonymized", metadata={"kvkk": True}, user_email=user.get("email"))
    return {"success": True, "message": "Misafir verileri KVKK kapsamında anonimleştirildi"}
