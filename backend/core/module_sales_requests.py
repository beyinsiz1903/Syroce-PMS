"""Platform sales inbox derived from the durable quote queue, never tenant alerts.

Reading a notification does not close a sales request. Receipts are per platform
administrator, and historical requests are visible without a notification backfill.
Callers must enforce platform-admin authorization before using the raw database.
"""

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

LEGACY_STATUSES = {"contacted": "in_progress", "qualified": "in_progress", "closed": "won", "rejected": "lost"}
STATUSES = ("new", "assigned", "in_progress", "quote_sent", "won", "lost")
OPEN_QUERY = {"status": {"$nin": ["won", "lost", "closed", "rejected"]}}


def status_query(status):
    if status == "open":
        return OPEN_QUERY.copy()
    if status == "all" or not status:
        return {}
    variants = [status, *(old for old, new in LEGACY_STATUSES.items() if new == status)]
    if status == "new":
        variants += [None, ""]
    return {"status": {"$in": variants}}


def normalize_request(row):
    return {**row, "status": LEGACY_STATUSES.get(row.get("status"), row.get("status") or "new")}


def follow_up_utc(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # The old datetime-local form persisted Turkish local times without offset.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Europe/Istanbul"))
    return parsed.astimezone(UTC).isoformat()


async def quote_summary(database):
    counts = await asyncio.gather(*(database.marketplace_quote_requests.count_documents(status_query(status)) for status in STATUSES))
    result = dict(zip(STATUSES, counts, strict=True))
    result["open"] = await database.marketplace_quote_requests.count_documents(OPEN_QUERY)
    result["total"] = await database.marketplace_quote_requests.count_documents({})
    return result


async def sales_inbox(database, user_id, *, limit=20):
    receipts = await database.marketplace_quote_request_reads.find({"user_id": user_id}, {"_id": 0, "request_id": 1}).to_list(None)
    seen = [row["request_id"] for row in receipts if row.get("request_id")]
    query = {**OPEN_QUERY, "id": {"$nin": seen}}
    rows, unread, opened, new = await asyncio.gather(
        database.marketplace_quote_requests.find(query, {"_id": 0}).sort([("created_at", -1), ("id", 1)]).limit(limit).to_list(limit),
        database.marketplace_quote_requests.count_documents(query),
        database.marketplace_quote_requests.count_documents(OPEN_QUERY),
        database.marketplace_quote_requests.count_documents(status_query("new")),
    )
    return {
        "notifications": [
            {
                "id": f"module-quote:{row['id']}",
                "request_id": row["id"],
                "type": "module_quote_request",
                "title": "Modül teklif talebi",
                "message": f"{row.get('tenant_name') or row.get('tenant_id') or 'Tesis'} · {row.get('product_name') or row.get('product_key') or 'Modül'}",
                "priority": "normal",
                "read": False,
                "created_at": row.get("created_at"),
                "action_url": "/admin/module-requests?" + urlencode({"request": row["id"]}),
            }
            for row in rows
        ],
        "unread_count": unread,
        "open_count": opened,
        "new_count": new,
    }


async def acknowledge_requests(database, user_id, request_ids):
    ids = list(dict.fromkeys(request_ids))
    existing = await database.marketplace_quote_requests.find({"id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(None)
    now = datetime.now(UTC).isoformat()
    # A stable document key makes concurrent acknowledgments idempotent even
    # before the optional compound query index has been created at startup.
    for row in existing:
        await database.marketplace_quote_request_reads.update_one(
            {"_id": f"{user_id}:quote:{row['id']}"},
            {"$setOnInsert": {"user_id": user_id, "request_id": row["id"], "read_at": now}},
            upsert=True,
        )
    return len(existing)
