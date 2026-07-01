"""Admin operations: backup/restore + email status/log/test."""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin
from backup_restore import create_backup, get_backup_schedule, list_backups, restore_backup
from db import db
from email_service import get_email_log, get_email_status, send_email
from helpers import create_auth_audit_log
from rate_limit import limiter
from schemas import BackupCreateRequest, BackupRestoreRequest

router = APIRouter()
logger = logging.getLogger("quickid")


@router.post("/api/admin/backup", tags=["Yedekleme"], summary="Veritabanı yedeği oluştur")
async def create_db_backup(req: BackupCreateRequest, user=Depends(require_admin)):
    try:
        result = await create_backup(db, created_by=user.get("email"), description=req.description)
        return {"success": True, "backup": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Yedekleme hatası: {str(e)}")


@router.get("/api/admin/backups", tags=["Yedekleme"], summary="Yedek listesi")
async def get_backups(user=Depends(require_admin)):
    backups = await list_backups(db)
    return {"backups": backups, "total": len(backups)}


@router.post("/api/admin/restore", tags=["Yedekleme"], summary="Yedekten geri yükle",
             description="DİKKAT: Mevcut verilerin üzerine yazar!")
@limiter.limit("3/hour")
async def restore_db_backup(request: Request, req: BackupRestoreRequest, user=Depends(require_admin)):
    # v109 Bug DAJ R3 (architect P1): backup restore can drop+rebuild audit_logs
    # → compromised admin token can rewind/erase forensic history. Defense layers:
    # 1. ENABLE_BACKUP_RESTORE env kill-switch (default disabled in production).
    # 2. Aggressive rate limit (3/hour).
    # 3. Pre-restore audit log + on-disk server log line that survives DB rewind.
    # 4. Post-restore audit log entry (lives in new audit_logs collection).
    actor_id = user.get("sub"); actor_email = user.get("email")
    ip = request.client.host if request and request.client else None

    if os.environ.get("ENABLE_BACKUP_RESTORE", "0") != "1":
        await create_auth_audit_log("backup_restore_blocked",
            actor_id=actor_id, actor_email=actor_email,
            outcome="blocked", reason="ENABLE_BACKUP_RESTORE env not set",
            metadata={"backup_id": req.backup_id}, ip_address=ip)
        logger.warning(
            "BACKUP_RESTORE_BLOCKED actor=%s ip=%s backup_id=%s reason=env-disabled",
            actor_email, ip, req.backup_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Geri yukleme bu ortamda devre disi. Aktiflestirme deploy zamani gerekir.",
        )

    await create_auth_audit_log("backup_restore_initiated",
        actor_id=actor_id, actor_email=actor_email,
        outcome="initiated", metadata={"backup_id": req.backup_id}, ip_address=ip)
    logger.warning(
        "BACKUP_RESTORE_INITIATED actor=%s ip=%s backup_id=%s — DB will be rewritten",
        actor_email, ip, req.backup_id,
    )

    try:
        result = await restore_backup(db, backup_id=req.backup_id, restore_by=actor_email)
    except ValueError as e:
        await create_auth_audit_log("backup_restore_failed",
            actor_id=actor_id, actor_email=actor_email,
            outcome="failed", reason=str(e),
            metadata={"backup_id": req.backup_id}, ip_address=ip)
        logger.warning(
            "BACKUP_RESTORE_FAILED actor=%s backup_id=%s err=%s",
            actor_email, req.backup_id, e,
        )
        raise HTTPException(status_code=404, detail=str(e))

    await create_auth_audit_log("backup_restore_completed",
        actor_id=actor_id, actor_email=actor_email,
        outcome="success",
        metadata={"backup_id": req.backup_id, "stats": result.get("stats", {})},
        ip_address=ip)
    logger.warning(
        "BACKUP_RESTORE_COMPLETED actor=%s backup_id=%s stats=%s",
        actor_email, req.backup_id, result.get("stats", {}),
    )
    return result


@router.get("/api/admin/backup-schedule", tags=["Yedekleme"], summary="Yedekleme planı")
async def backup_schedule(user=Depends(require_admin)):
    return get_backup_schedule()


@router.get("/api/admin/email-status", tags=["E-posta"], summary="E-posta servis durumu")
async def email_status_endpoint(user=Depends(require_admin)):
    return get_email_status()


@router.get("/api/admin/email-log", tags=["E-posta"], summary="E-posta gonderim logu")
async def email_log_endpoint(limit: int = Query(50, ge=1, le=200), user=Depends(require_admin)):
    return {"emails": get_email_log(limit), "total": len(get_email_log(limit))}


@router.post("/api/admin/email-test", tags=["E-posta"], summary="Test e-postasi gonder")
async def send_test_email(user=Depends(require_admin)):
    result = await send_email(
        to=user.get("email", "admin@quickid.com"),
        subject="Quick ID - Test E-postasi",
        body_html="<h2>Test basarili!</h2><p>E-posta servisi calisiyor.</p>",
        template_name="test",
    )
    return {"success": True, "result": result}
