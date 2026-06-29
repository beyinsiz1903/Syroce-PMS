import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["uploads"])

_backend_dir = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(_backend_dir / "uploads"))).resolve()

@router.get("/api/uploads/{path:path}")
async def get_upload(
    path: str,
    current_user: User = Depends(get_current_user)
):
    """
    Securely serve uploaded files.
    Supports both legacy physical path URLs (e.g. {tenant_id}/rooms/...)
    and the new upload_id metadata layer.
    """
    if not path:
        raise HTTPException(status_code=400, detail="Invalid path")

    target_file_path: Path | None = None

    # Check if this is an upload_id (no slashes)
    if "/" not in path:
        upload_id = path
        upload_record = await db.uploads.find_one({"_id": upload_id})
        if not upload_record:
            raise HTTPException(status_code=404, detail="File not found")

        # Verify ownership / tenant authorization
        if upload_record.get("tenant_id") != current_user.tenant_id and current_user.role != "super_admin":
            raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this file")

        target_file_path = UPLOAD_DIR / upload_record["relative_path"]
    else:
        # Legacy path-based routing
        # Format 1: {tenant_id}/rooms/{room_id}/{filename}
        # Format 2: vendors/{vendor_id}/products/{filename}
        parts = path.split("/")

        if parts[0] == "vendors":
            if len(parts) < 3:
                raise HTTPException(status_code=400, detail="Invalid vendor path")
            # If we had a specific vendor role check, it would go here.
        else:
            # Tenant upload
            target_tenant_id = parts[0]
            if target_tenant_id != current_user.tenant_id and current_user.role != "super_admin":
                raise HTTPException(status_code=403, detail="Forbidden: Tenant mismatch")

        target_file_path = UPLOAD_DIR / path

    # Strict path traversal protection
    try:
        safe_path = target_file_path.resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path structure")

    if not str(safe_path).startswith(str(UPLOAD_DIR) + os.sep) and safe_path != UPLOAD_DIR:
        logger.warning(f"Path traversal attempt by user {current_user.id}: {path}")
        raise HTTPException(status_code=400, detail="Invalid path")

    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Determine the file's owning tenant for audit logging
    file_owner_tenant = None
    if "/" not in path and 'upload_record' in locals():
        file_owner_tenant = upload_record.get("tenant_id")
    elif "vendors" not in parts:
        file_owner_tenant = parts[0]

    if current_user.role == "super_admin" and current_user.tenant_id != file_owner_tenant:
        try:
            await db.audit_logs.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "target_tenant_id": file_owner_tenant,
                "user_id": current_user.id,
                "user_email": getattr(current_user, "email", "unknown"),
                "action": "super_admin_file_access",
                "resource_type": "upload",
                "resource_id": path,
                "timestamp": datetime.now(UTC).isoformat(),
            })
        except Exception as e:
            logger.warning(f"Failed to audit log super admin file access: {e}")

    logger.info(f"User {current_user.id} accessed upload {safe_path.name}")
    return FileResponse(str(safe_path))
