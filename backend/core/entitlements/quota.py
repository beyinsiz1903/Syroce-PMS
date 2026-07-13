from datetime import datetime, UTC
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from core.database import db

class QuotaExceededException(Exception):
    pass

async def _ensure_quota_doc(tenant_id: str, module_key: str, metric: str) -> None:
    try:
        await db.entitlement_quota_usage.update_one(
            {
                "tenant_id": tenant_id,
                "module_key": module_key,
                "metric": metric
            },
            {
                "$setOnInsert": {
                    "used": 0,
                    "resources": [],
                    "created_at": datetime.now(UTC)
                }
            },
            upsert=True
        )
    except DuplicateKeyError:
        pass

async def reserve_quota(tenant_id: str, module_key: str, metric: str, resource_id: str, limit: int, force: bool = False) -> dict:
    """
    Atomically reserves a quota slot.
    If force=True, it will increment the quota even if it exceeds the limit.
    Idempotent: if resource_id is already reserved, returns safely.
    """
    if limit <= 0 and not force:
        raise QuotaExceededException(f"Kota limiti {limit} oldugu icin islem yapilamaz.")

    await _ensure_quota_doc(tenant_id, module_key, metric)
    now = datetime.now(UTC)

    query = {
        "tenant_id": tenant_id,
        "module_key": module_key,
        "metric": metric,
        "resources": {"$ne": resource_id}
    }
    if not force:
        query["used"] = {"$lt": limit}

    doc = await db.entitlement_quota_usage.find_one_and_update(
        query,
        {
            "$inc": {"used": 1},
            "$addToSet": {"resources": resource_id},
            "$set": {"updated_at": now}
        },
        return_document=ReturnDocument.AFTER
    )

    if not doc:
        # It failed. Let's check why.
        current = await db.entitlement_quota_usage.find_one({
            "tenant_id": tenant_id,
            "module_key": module_key,
            "metric": metric
        })
        # If it's already in the list, it's an idempotent success
        if current and resource_id in current.get("resources", []):
            return current
            
        raise QuotaExceededException(f"Maksimum limit ({limit}) asildi.")
    
    return doc

async def release_quota(tenant_id: str, module_key: str, metric: str, resource_id: str) -> None:
    """
    Atomically releases a quota slot.
    Idempotent: if resource_id is not found, does nothing.
    """
    now = datetime.now(UTC)
    await db.entitlement_quota_usage.update_one(
        {
            "tenant_id": tenant_id,
            "module_key": module_key,
            "metric": metric,
            "resources": resource_id,
            "used": {"$gt": 0}
        },
        {
            "$inc": {"used": -1},
            "$pull": {"resources": resource_id},
            "$set": {"updated_at": now}
        }
    )
