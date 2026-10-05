"""Concurrency-safe numeric numbering for kitchen-display tickets."""

import logging
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.database import db

_KITCHEN_COUNTER_INDEX_READY = False


async def _ensure_kitchen_counter_index() -> None:
    global _KITCHEN_COUNTER_INDEX_READY
    if _KITCHEN_COUNTER_INDEX_READY:
        return
    try:
        await db.pos_kitchen_counters.create_index(
            [("tenant_id", 1)],
            unique=True,
            name="uq_kitchen_order_counter",
        )
        _KITCHEN_COUNTER_INDEX_READY = True
    except Exception as exc:  # pragma: no cover - index race/permission
        logging.warning("kitchen order counter index ensure failed: %s", exc)


async def next_kitchen_order_number(tenant_id: str) -> int:
    """Return a tenant-scoped, monotonic KDS number.

    Historical rows used values such as ``ORD-202605...``. MongoDB's mixed-type
    sorting can put those strings ahead of numeric rows, which made the old
    ``int(last_value)`` fallback issue number 1 repeatedly. Seed/synchronise a
    dedicated atomic counter from numeric legacy rows only.
    """
    await _ensure_kitchen_counter_index()
    numeric_rows = (
        await db.kitchen_orders.find(
            {"tenant_id": tenant_id, "order_number": {"$type": "number"}},
            {"order_number": 1},
        )
        .sort("order_number", -1)
        .limit(1)
        .to_list(1)
    )
    numeric_max = int(numeric_rows[0]["order_number"]) if numeric_rows else 0
    key = {"tenant_id": tenant_id}

    # $max keeps a newly introduced counter compatible with existing numeric
    # tickets and also repairs a counter that has fallen behind. The unique
    # tenant index makes concurrent first use safe.
    for _ in range(3):
        try:
            await db.pos_kitchen_counters.update_one(
                key,
                {
                    "$max": {"seq": numeric_max},
                    "$setOnInsert": {"created_at": datetime.now(UTC)},
                },
                upsert=True,
            )
            break
        except DuplicateKeyError:
            continue

    doc = await db.pos_kitchen_counters.find_one_and_update(
        key,
        {"$inc": {"seq": 1}, "$set": {"updated_at": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:  # defensive: only possible when all counter upserts failed
        raise RuntimeError("kitchen order counter could not be initialized")
    return int(doc["seq"])
