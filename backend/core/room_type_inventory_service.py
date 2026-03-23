"""
Room-Type Inventory Service — Phase C.1 Read-Only Materialized View
====================================================================
ADR-003: Aggregates room_night_locks into room-type-level availability.

Layer 2 of the 3-layer inventory model:
  Layer 1: room_night_locks (physical rooms, ADR-001)
  Layer 2: room_type_inventory (this module — aggregated sellable counts)
  Layer 3: channel_inventory (Phase C.2, future)

Phase C.1 is READ-ONLY:
  - No booking flow changes
  - Reconciliation worker computes values every 5 minutes
  - API serves the materialized view
  - Accuracy is validated against ad-hoc channel manager calculation

INV-7: room_type_inventory.sellable == physical_total - count(locks for that type+date)
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import db

logger = logging.getLogger("core.room_type_inventory")


async def ensure_room_type_inventory_indexes() -> None:
    """Create indexes for room_type_inventory collection."""
    coll = db.room_type_inventory
    indexes = [
        {
            "keys": [("tenant_id", 1), ("room_type", 1), ("date", 1)],
            "name": "ux_tenant_type_date",
            "unique": True,
        },
        {
            "keys": [("tenant_id", 1), ("date", 1)],
            "name": "idx_tenant_date",
        },
        {
            "keys": [("tenant_id", 1), ("room_type", 1), ("date", 1), ("sellable", 1)],
            "name": "idx_tenant_type_date_sellable",
        },
    ]
    for idx in indexes:
        try:
            await coll.create_index(
                idx["keys"],
                name=idx["name"],
                unique=idx.get("unique", False),
                background=True,
            )
        except Exception as e:
            if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
                pass
            else:
                logger.warning("Index %s creation failed: %s", idx["name"], e)
    logger.info("room_type_inventory indexes ensured")


async def compute_room_type_inventory(
    tenant_id: str,
    date: str,
) -> List[Dict[str, Any]]:
    """
    Compute room-type inventory for a single date by aggregating room_night_locks.

    Returns a list of dicts, one per room type:
      {tenant_id, room_type, date, physical_total, locked_booking,
       locked_hold, locked_ooo, locked_oos, sellable, last_computed_at, computation_source}
    """
    now = datetime.now(timezone.utc).isoformat()

    # Step 1: Count active rooms per type for this tenant
    room_type_pipeline = [
        {"$match": {"tenant_id": tenant_id, "is_active": True}},
        {"$group": {"_id": "$room_type", "count": {"$sum": 1}, "room_ids": {"$push": "$id"}}},
    ]
    room_groups = await db.rooms.aggregate(room_type_pipeline).to_list(200)

    # Build room_id → room_type lookup for this tenant
    room_id_to_type: Dict[str, str] = {}
    type_totals: Dict[str, int] = {}
    for group in room_groups:
        rt = group["_id"]
        if not rt:
            continue
        type_totals[rt] = group["count"]
        for rid in group.get("room_ids", []):
            room_id_to_type[rid] = rt

    if not type_totals:
        return []

    # Step 2: Get all locks for this date using aggregation with lookup
    lock_pipeline = [
        {"$match": {"tenant_id": tenant_id, "night_date": date}},
        {"$group": {
            "_id": {"room_id": "$room_id", "lock_type": "$lock_type"},
            "count": {"$sum": 1},
        }},
    ]
    lock_groups = await db.room_night_locks.aggregate(lock_pipeline).to_list(5000)

    # Step 3: Aggregate by room type
    type_locks: Dict[str, Dict[str, int]] = {}
    for lg in lock_groups:
        room_id = lg["_id"]["room_id"]
        lock_type = lg["_id"]["lock_type"]
        rt = room_id_to_type.get(room_id)
        if not rt:
            continue
        if rt not in type_locks:
            type_locks[rt] = {"booking": 0, "hold": 0, "ooo": 0, "oos": 0, "maintenance": 0}
        if lock_type in type_locks[rt]:
            type_locks[rt][lock_type] += lg["count"]

    # Step 4: Build result
    results = []
    for rt, total in type_totals.items():
        locks = type_locks.get(rt, {})
        locked_booking = locks.get("booking", 0)
        locked_hold = locks.get("hold", 0)
        locked_ooo = locks.get("ooo", 0)
        locked_oos = locks.get("oos", 0) + locks.get("maintenance", 0)
        sellable = max(0, total - locked_booking - locked_hold - locked_ooo - locked_oos)

        results.append({
            "tenant_id": tenant_id,
            "room_type": rt,
            "date": date,
            "physical_total": total,
            "locked_booking": locked_booking,
            "locked_hold": locked_hold,
            "locked_ooo": locked_ooo,
            "locked_oos": locked_oos,
            "sellable": sellable,
            "last_computed_at": now,
            "computation_source": "reconciliation",
        })

    return results


async def reconcile_date_range(
    tenant_id: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """
    Run reconciliation for a date range. Upserts into room_type_inventory.

    Returns summary: {dates_processed, types_processed, drift_detected, drifts}
    """
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    dates_processed = 0
    types_processed = 0
    drift_count = 0
    drifts = []

    current = start
    while current <= end:
        date_str = current.isoformat()
        inventory = await compute_room_type_inventory(tenant_id, date_str)

        for item in inventory:
            # Check for drift against existing record
            existing = await db.room_type_inventory.find_one(
                {"tenant_id": tenant_id, "room_type": item["room_type"], "date": date_str},
                {"_id": 0, "sellable": 1, "locked_booking": 1},
            )
            if existing and existing.get("sellable") != item["sellable"]:
                drift_count += 1
                drifts.append({
                    "room_type": item["room_type"],
                    "date": date_str,
                    "old_sellable": existing.get("sellable"),
                    "new_sellable": item["sellable"],
                })

            # Upsert
            await db.room_type_inventory.update_one(
                {"tenant_id": tenant_id, "room_type": item["room_type"], "date": date_str},
                {"$set": item},
                upsert=True,
            )
            types_processed += 1

        dates_processed += 1
        current += timedelta(days=1)

    # Log drifts to event timeline if any
    if drift_count > 0:
        try:
            from controlplane.timeline_writer import get_timeline_writer
            writer = get_timeline_writer()
            await writer.append(
                tenant_id=tenant_id,
                correlation_id=f"recon-{datetime.now(timezone.utc).isoformat()}",
                entity_type="inventory",
                entity_id="room_type_inventory",
                stage="inventory_drift_detected",
                status="warning",
                source="room_type_inventory_reconciliation",
                metadata={
                    "drift_count": drift_count,
                    "date_range": f"{start_date} to {end_date}",
                    "drifts": drifts[:10],
                },
            )
        except Exception as e:
            logger.debug("Timeline drift event failed: %s", e)

    return {
        "dates_processed": dates_processed,
        "types_processed": types_processed,
        "drift_detected": drift_count,
        "drifts": drifts,
    }


async def get_room_type_inventory(
    tenant_id: str,
    date: str,
    room_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get room-type inventory for a date. Returns from materialized view.
    If no data exists, computes on-the-fly.
    """
    query: Dict[str, Any] = {"tenant_id": tenant_id, "date": date}
    if room_type:
        query["room_type"] = room_type

    results = await db.room_type_inventory.find(
        query, {"_id": 0}
    ).to_list(200)

    if not results:
        # Compute on-the-fly if materialized view is empty
        results = await compute_room_type_inventory(tenant_id, date)
        # Store for future reads
        for item in results:
            try:
                await db.room_type_inventory.update_one(
                    {"tenant_id": tenant_id, "room_type": item["room_type"], "date": date},
                    {"$set": item},
                    upsert=True,
                )
            except Exception:
                pass

    if room_type:
        results = [r for r in results if r.get("room_type") == room_type]

    return results


async def get_inventory_summary(
    tenant_id: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """
    Get aggregated inventory summary across a date range.
    Returns: {room_types: [...], date_range: {start, end}, total_sellable, total_physical}
    """
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    all_items = await db.room_type_inventory.find(
        {
            "tenant_id": tenant_id,
            "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        },
        {"_id": 0},
    ).to_list(5000)

    # Aggregate by room type
    type_summary: Dict[str, Dict[str, Any]] = {}
    for item in all_items:
        rt = item["room_type"]
        if rt not in type_summary:
            type_summary[rt] = {
                "room_type": rt,
                "physical_total": item.get("physical_total", 0),
                "min_sellable": item.get("sellable", 0),
                "max_sellable": item.get("sellable", 0),
                "avg_occupancy_pct": 0,
                "dates_with_data": 0,
                "total_locked": 0,
            }
        s = type_summary[rt]
        sellable = item.get("sellable", 0)
        physical = item.get("physical_total", 0) or 1
        locked = (item.get("locked_booking", 0) + item.get("locked_hold", 0) +
                  item.get("locked_ooo", 0) + item.get("locked_oos", 0))
        s["min_sellable"] = min(s["min_sellable"], sellable)
        s["max_sellable"] = max(s["max_sellable"], sellable)
        s["total_locked"] += locked
        s["dates_with_data"] += 1
        s["avg_occupancy_pct"] = round(
            (s["total_locked"] / (s["dates_with_data"] * physical)) * 100, 1
        ) if s["dates_with_data"] > 0 else 0

    total_sellable = sum(i.get("sellable", 0) for i in all_items)
    total_physical = sum(i.get("physical_total", 0) for i in all_items)

    return {
        "tenant_id": tenant_id,
        "date_range": {"start": start_date, "end": end_date},
        "room_types": list(type_summary.values()),
        "total_sellable_room_nights": total_sellable,
        "total_physical_room_nights": total_physical,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Background Reconciliation Worker ────────────────────────────────

class RoomTypeInventoryWorker:
    """Background worker that reconciles room_type_inventory every 5 minutes."""

    def __init__(self, interval_seconds: int = 300):
        self._interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("RoomTypeInventoryWorker started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("RoomTypeInventoryWorker stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._run_once()
            except Exception as e:
                logger.error("RoomTypeInventoryWorker error: %s", e)
            await asyncio.sleep(self._interval)

    async def _run_once(self) -> None:
        """Run reconciliation for all tenants, today + 30 days."""
        tenants = await db.organizations.find({}, {"_id": 0, "id": 1}).to_list(100)
        if not tenants:
            # Fallback: get tenant from rooms
            room = await db.rooms.find_one({}, {"_id": 0, "tenant_id": 1})
            if room and room.get("tenant_id"):
                tenants = [{"id": room["tenant_id"]}]

        today = datetime.now(timezone.utc).date()
        start_date = today.isoformat()
        end_date = (today + timedelta(days=30)).isoformat()

        for tenant in tenants:
            tid = tenant.get("id")
            if not tid:
                continue
            try:
                result = await reconcile_date_range(tid, start_date, end_date)
                if result["drift_detected"] > 0:
                    logger.warning(
                        "Inventory drift detected for tenant %s: %d drifts",
                        tid, result["drift_detected"],
                    )
                else:
                    logger.debug(
                        "Reconciliation OK for tenant %s: %d dates, %d types",
                        tid, result["dates_processed"], result["types_processed"],
                    )
            except Exception as e:
                logger.error("Reconciliation failed for tenant %s: %s", tid, e)


# Singleton
_worker: Optional[RoomTypeInventoryWorker] = None


def get_inventory_worker() -> RoomTypeInventoryWorker:
    global _worker
    if _worker is None:
        _worker = RoomTypeInventoryWorker()
    return _worker
