import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.supplies_market.vendor_auth import get_current_vendor_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["uploads"])

_backend_dir = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(_backend_dir / "uploads"))).resolve()

security = HTTPBearer(auto_error=False)

async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User | None:
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None

async def get_optional_vendor(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str | None:
    try:
        return await get_current_vendor_id(credentials)
    except HTTPException:
        return None


@router.get("/api/uploads/{path:path}")
async def get_upload(
    path: str,
    optional_user: User | None = Depends(get_optional_user),
    optional_vendor_id: str | None = Depends(get_optional_vendor)
):
    """
    Securely serve uploaded files.
    Supports both legacy physical path URLs (e.g. {tenant_id}/rooms/...)
    and the new upload_id metadata layer.
    """
    if not path:
        raise HTTPException(status_code=400, detail="Invalid path")
        
    if not optional_user and not optional_vendor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    target_file_path: Path | None = None

    # Check if this is an upload_id (no slashes)
    if "/" not in path:
        upload_id = path
        upload_record = await db.uploads.find_one({"_id": upload_id})
        if not upload_record:
            raise HTTPException(status_code=404, detail="File not found")

        owner_type = upload_record.get("owner_type", "tenant")
        
        # Verify ownership / tenant authorization
        if owner_type == "vendor":
            # If a vendor tries to access a file, they MUST own it
            if optional_vendor_id and upload_record.get("vendor_id") != optional_vendor_id:
                # Log unauthorized cross-vendor access
                try:
                    await db.audit_logs.insert_one({
                        "id": str(uuid.uuid4()),
                        "vendor_id": optional_vendor_id,
                        "target_vendor_id": upload_record.get("vendor_id"),
                        "action": "unauthorized_vendor_file_access",
                        "resource_type": "upload",
                        "resource_id": path,
                        "timestamp": datetime.now(UTC).isoformat(),
                    })
                except Exception as e:
                    logger.warning(f"Failed to log vendor access violation: {e}")
                raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this vendor file")
            # If a user tries to access a vendor file, allow it ONLY if it is marketplace_public
            elif optional_user:
                visibility = upload_record.get("visibility")
                if visibility != "marketplace_public":
                    raise HTTPException(status_code=403, detail="Forbidden: This vendor file is not public")
            elif not optional_user and not optional_vendor_id:
                # Handled by the check at the top, but for completeness
                raise HTTPException(status_code=403, detail="Forbidden")
                
        else: # owner_type == "tenant"
            # Vendors cannot access tenant files
            if not optional_user:
                raise HTTPException(status_code=403, detail="Forbidden: Vendors cannot access tenant files")
                
            if upload_record.get("tenant_id") != optional_user.tenant_id and optional_user.role != "super_admin":
                raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this file")

        target_file_path = UPLOAD_DIR / upload_record["relative_path"]
    else:
        # Legacy path-based routing
        # Format 1: {tenant_id}/rooms/{room_id}/{filename}
        # Format 2: vendors/{vendor_id}/products/{filename}
        parts = path.split("/")

        if parts[0] == "vendors":
            if len(parts) < 4 or parts[2] != "products":
                raise HTTPException(status_code=400, detail="Invalid vendor path")
            
            target_vendor_id = parts[1]
            if optional_vendor_id and target_vendor_id != optional_vendor_id:
                # Log unauthorized cross-vendor access for legacy paths too
                try:
                    await db.audit_logs.insert_one({
                        "id": str(uuid.uuid4()),
                        "vendor_id": optional_vendor_id,
                        "target_vendor_id": target_vendor_id,
                        "action": "unauthorized_vendor_file_access",
                        "resource_type": "upload",
                        "resource_id": path,
                        "timestamp": datetime.now(UTC).isoformat(),
                    })
                except Exception as e:
                    logger.warning(f"Failed to log vendor access violation (legacy): {e}")
                raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this vendor file")
                
            # If user, allow (implicit marketplace_public since format mandates 'products')
            if not optional_user and not optional_vendor_id:
                raise HTTPException(status_code=403, detail="Forbidden")
        else:
            # Tenant upload
            if not optional_user:
                raise HTTPException(status_code=403, detail="Forbidden: Vendors cannot access tenant files")
                
            target_tenant_id = parts[0]
            if target_tenant_id != optional_user.tenant_id and optional_user.role != "super_admin":
                raise HTTPException(status_code=403, detail="Forbidden: Tenant mismatch")

        target_file_path = UPLOAD_DIR / path

    # Strict path traversal protection
    try:
        safe_path = target_file_path.resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path structure")

    if not str(safe_path).startswith(str(UPLOAD_DIR) + os.sep) and safe_path != UPLOAD_DIR:
        user_identifier = optional_user.id if optional_user else f"vendor_{optional_vendor_id}"
        logger.warning(f"Path traversal attempt by user {user_identifier}: {path}")
        raise HTTPException(status_code=400, detail="Invalid path")

    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Determine the file's owning tenant for audit logging (super admin only)
    if optional_user and optional_user.role == "super_admin":
        file_owner_tenant = None
        if "/" not in path and 'upload_record' in locals() and upload_record.get("owner_type") != "vendor":
            file_owner_tenant = upload_record.get("tenant_id")
        elif "vendors" not in locals().get('parts', []):
            parts = path.split("/")
            if len(parts) > 0 and parts[0] != "vendors":
                file_owner_tenant = parts[0]
            
        if file_owner_tenant and optional_user.tenant_id != file_owner_tenant:
            try:
                await db.audit_logs.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": optional_user.tenant_id,
                    "target_tenant_id": file_owner_tenant,
                    "user_id": optional_user.id,
                    "user_email": getattr(optional_user, "email", "unknown"),
                    "action": "super_admin_file_access",
                    "resource_type": "upload",
                    "resource_id": path,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
            except Exception as e:
                logger.warning(f"Failed to audit log super admin file access: {e}")

    return FileResponse(str(safe_path))
