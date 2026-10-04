"""Canonical, tenant-scoped operational truth for the open PMS day.

Dashboard cards, AI summaries and night-audit preparation must not calculate
occupancy from different clocks or inventory filters.  This module owns that
small read contract so every consumer receives the same business date,
sellable-room scope and reservation overlap semantics.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from core.business_date_service import ensure_business_date_initialized
from core.database import db

ACTIVE_STAY_STATUSES = {"confirmed", "guaranteed", "checked_in"}


def active_room_filter(tenant_id: str) -> dict[str, Any]:
    """Return the one inventory scope used by operational PMS surfaces."""

    return {
        "tenant_id": tenant_id,
        "$and": [
            {"$or": [{"is_virtual": False}, {"is_virtual": {"$exists": False}}]},
            {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
        ],
    }


def _date_only(value: Any) -> str:
    return str(value or "")[:10]


async def build_operational_snapshot(
    tenant_id: str,
    *,
    business_date: str | None = None,
    database=None,
) -> dict[str, Any]:
    """Build the authoritative operational snapshot for a tenant and PMS day."""

    database = database or db
    if business_date is None:
        state = await ensure_business_date_initialized(database, tenant_id)
        business_date = _date_only(state.get("business_date"))
    else:
        business_date = _date_only(business_date)
    if len(business_date) != 10:
        raise RuntimeError(f"PMS business date is invalid for tenant {tenant_id}")

    room_rows = await database.rooms.aggregate(
        [
            {"$match": active_room_filter(tenant_id)},
            {"$group": {"_id": "$status", "count": {"$sum": 1}, "room_ids": {"$addToSet": "$id"}}},
        ]
    ).to_list(100)
    room_status = {str(row.get("_id") or "unknown").lower(): int(row.get("count") or 0) for row in room_rows}
    active_room_ids = {
        str(room_id)
        for row in room_rows
        for room_id in row.get("room_ids", [])
        if room_id
    }
    total_rooms = sum(room_status.values())

    bookings = await database.bookings.find(
        {"tenant_id": tenant_id, "status": {"$in": sorted(ACTIVE_STAY_STATUSES)}},
        {"_id": 0, "id": 1, "room_id": 1, "status": 1, "check_in": 1, "check_out": 1},
    ).to_list(10_000)

    occupied_stays = []
    arrivals = 0
    departures = 0
    for booking in bookings:
        check_in = _date_only(booking.get("check_in"))
        check_out = _date_only(booking.get("check_out"))
        if check_in <= business_date < check_out:
            occupied_stays.append(booking)
        if check_in == business_date:
            arrivals += 1
        if check_out == business_date:
            departures += 1

    # One room may have multiple linked booking records.  Prefer assigned room
    # identities for occupancy, while retaining unassigned stays as operational
    # exceptions rather than silently dropping them from the occupied count.
    assigned_room_ids = {
        str(item.get("room_id"))
        for item in occupied_stays
        if item.get("room_id") and str(item.get("room_id")) in active_room_ids
    }
    scoped_stays = [
        item
        for item in occupied_stays
        if not item.get("room_id") or str(item.get("room_id")) in active_room_ids
    ]
    unassigned_stays = sum(not item.get("room_id") for item in scoped_stays)
    out_of_scope_assigned_stays = len(occupied_stays) - len(scoped_stays)
    in_house_stays = sum(item.get("status") == "checked_in" for item in scoped_stays)
    occupied_rooms = min(total_rooms, len(assigned_room_ids) + unassigned_stays)
    occupancy_rate = round(min((occupied_rooms / total_rooms * 100), 100.0), 2) if total_rooms else 0.0
    calendar_date = datetime.now(UTC).date().isoformat()
    as_of = datetime.now(UTC).isoformat()

    identity = {
        "tenant_id": tenant_id,
        "business_date": business_date,
        "total_rooms": total_rooms,
        "occupied_rooms": occupied_rooms,
        "arrivals": arrivals,
        "departures": departures,
        "in_house_stays": in_house_stays,
        "total_guests": len(scoped_stays),
    }
    snapshot_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]

    return {
        "snapshot_id": snapshot_id,
        "as_of": as_of,
        "business_date": business_date,
        "calendar_date": calendar_date,
        "inventory_scope": "active_non_virtual_rooms",
        "total_rooms": total_rooms,
        "occupied_rooms": occupied_rooms,
        "available_rooms": max(0, total_rooms - occupied_rooms),
        "occupancy_rate": occupancy_rate,
        "today_checkins": arrivals,
        "today_checkouts": departures,
        "total_guests": len(scoped_stays),
        "in_house_stays": in_house_stays,
        "unassigned_occupied_stays": unassigned_stays,
        "out_of_scope_assigned_stays": out_of_scope_assigned_stays,
        "room_status": room_status,
    }
