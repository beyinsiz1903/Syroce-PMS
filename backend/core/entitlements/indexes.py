import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

async def ensure_entitlement_indexes(db):
    """
    Ensures entitlement indexes exist. Handles duplicate quota records safely by merging their resources.
    This should be called during application startup (e.g. from subscriptions.py's ensure_indexes).
    """
    # Entitlement Quota Deduplication & Index
    pipeline = [
        {"$group": {
            "_id": {"tenant_id": "$tenant_id", "module_key": "$module_key", "metric": "$metric"},
            "count": {"$sum": 1},
            "docs": {"$push": "$_id"},
            "all_resources": {"$push": "$resources"}
        }},
        {"$match": {"count": {"$gt": 1}}}
    ]
    async for dup in db.entitlement_quota_usage.aggregate(pipeline):
        docs = dup["docs"]
        all_resources_nested = dup["all_resources"]

        # Merge resources uniquely
        merged_resources = set()
        for res_list in all_resources_nested:
            if res_list:
                merged_resources.update(res_list)

        merged_resources_list = list(merged_resources)
        merged_used = len(merged_resources_list)

        keeper_id = docs[0]
        docs_to_delete = docs[1:]

        logger.warning(f"[STARTUP] Found duplicate quota docs for {dup['_id']}. Merging into {keeper_id} and deleting the rest.")

        # Update canonical doc
        await db.entitlement_quota_usage.update_one(
            {"_id": keeper_id},
            {"$set": {
                "resources": merged_resources_list,
                "used": merged_used,
                "updated_at": datetime.now(UTC)
            }}
        )

        # Delete duplicates
        await db.entitlement_quota_usage.delete_many({"_id": {"$in": docs_to_delete}})

    await db.entitlement_quota_usage.create_index(
        [("tenant_id", 1), ("module_key", 1), ("metric", 1)],
        unique=True,
        name="uniq_entitlement_quota_metric",
    )

    await db.pos_outlets.create_index(
        [("tenant_id", 1), ("client_request_id", 1)],
        unique=True,
        partialFilterExpression={"client_request_id": {"$type": "string"}},
        name="uniq_pos_outlets_client_request_id",
    )
