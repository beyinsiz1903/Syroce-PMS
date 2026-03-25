"""
Field Encryption Operations Router.

Provides API endpoints for:
  - Encryption status across collections
  - Triggering migration of existing plaintext data
  - Migration progress tracking
  - Hash index management
  - Audit trail for encryption operations
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import _raw_db as system_db
from core.security import get_current_user
from models.schemas import User
from security.field_encryption import get_field_encryption_service

logger = logging.getLogger("security.field_encryption_router")

router = APIRouter(
    prefix="/api/ops/field-encryption",
    tags=["field-encryption-ops"],
)


def _require_ops_role(user: User = Depends(get_current_user)) -> User:
    """Only super_admin can manage field encryption."""
    if user.role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Yetkisiz: field encryption ops icin super_admin veya admin rolu gerekli")
    return user


@router.get("/status")
async def get_encryption_status(user: User = Depends(_require_ops_role)):
    """Return encryption coverage per collection."""
    svc = get_field_encryption_service()
    status = await svc.get_encryption_status(system_db)
    return {
        "status": "ok",
        "config": svc.get_config(),
        "collections": status,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.post("/migrate/{collection_name}")
async def trigger_migration(
    collection_name: str,
    batch_size: int = 100,
    user: User = Depends(_require_ops_role),
):
    """Trigger encryption migration for a specific collection."""
    svc = get_field_encryption_service()

    if collection_name not in svc.get_config()["collections"]:
        raise HTTPException(
            status_code=400,
            detail=f"Koleksiyon yapilandirmada yok: {collection_name}",
        )

    # Audit the migration trigger
    await system_db["field_encryption_audit"].insert_one({
        "action": "migration_triggered",
        "collection": collection_name,
        "actor": user.email,
        "actor_role": user.role,
        "batch_size": batch_size,
        "timestamp": datetime.now(UTC).isoformat(),
    })

    result = await svc.migrate_collection(
        system_db,
        collection_name,
        batch_size=batch_size,
    )
    return {"status": "ok", "migration": result}


@router.get("/progress")
async def get_migration_progress(user: User = Depends(_require_ops_role)):
    """Return migration progress for all collections."""
    cursor = system_db["field_encryption_progress"].find({}, {"_id": 0})
    progress = await cursor.to_list(100)
    return {"status": "ok", "progress": progress}


@router.post("/ensure-indexes")
async def ensure_indexes(user: User = Depends(_require_ops_role)):
    """Create hash indexes for encrypted searchable fields."""
    svc = get_field_encryption_service()
    created = await svc.ensure_hash_indexes(system_db)
    return {"status": "ok", "indexes_created": created}


@router.get("/audit")
async def get_encryption_audit(
    limit: int = 50,
    user: User = Depends(_require_ops_role),
):
    """Return encryption operation audit trail."""
    cursor = (
        system_db["field_encryption_audit"]
        .find({}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )
    audit_entries = await cursor.to_list(limit)
    return {"status": "ok", "audit": audit_entries, "count": len(audit_entries)}


@router.get("/config")
async def get_encryption_config(user: User = Depends(_require_ops_role)):
    """Return current field encryption configuration."""
    svc = get_field_encryption_service()
    return {"status": "ok", "config": svc.get_config()}
