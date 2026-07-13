import asyncio
import logging
from datetime import datetime, UTC
from core.database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def backfill_pos_quota() -> None:
    logger.info("Starting POS quota backfill...")
    
    # 1. Ensure unique index
    await db.entitlement_quota_usage.create_index(
        [("tenant_id", 1), ("module_key", 1), ("metric", 1)],
        unique=True
    )
    
    # 2. Count active/inactive pos outlets per tenant
    pipeline = [
        {"$match": {
            "tenant_id": {"$type": "string", "$ne": ""},
            "id": {"$type": "string", "$ne": ""},
            "status": {"$ne": "deleted"}
        }},
        {"$group": {
            "_id": "$tenant_id",
            "resources": {"$addToSet": "$id"}
        }},
        {"$project": {
            "tenant_id": "$_id",
            "resources": 1,
            "count": {"$size": "$resources"}
        }}
    ]
    
    processed = 0
    async for tenant_data in db.pos_outlets.aggregate(pipeline):
        tenant_id = tenant_data["tenant_id"]
        count = tenant_data["count"]
        resources = tenant_data["resources"]
        
        # 3. Upsert into entitlement_quota_usage
        await db.entitlement_quota_usage.update_one(
            {
                "tenant_id": tenant_id,
                "module_key": "pos_fnb",
                "metric": "outlets"
            },
            {
                "$set": {
                    "used": count,
                    "resources": resources,
                    "updated_at": datetime.now(UTC)
                },
                "$setOnInsert": {
                    "created_at": datetime.now(UTC)
                }
            },
            upsert=True
        )
        processed += 1
        
    logger.info(f"Backfilled POS quota for {processed} tenants.")

if __name__ == "__main__":
    asyncio.run(backfill_pos_quota())
