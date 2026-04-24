"""
Room-Type Inventory API — Phase C.1 Read-Only View
====================================================
ADR-003: Exposes room-type-level availability as a materialized view.

Endpoints:
  GET  /api/inventory/room-types          — Get room-type availability for a date
  GET  /api/inventory/room-types/summary  — Get date-range summary
  POST /api/inventory/room-types/reconcile — Trigger manual reconciliation
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import db
from modules.pms_core.role_permission_service import require_op  # v92.2 DW

logger = logging.getLogger("routers.inventory")

router = APIRouter(prefix="/api/inventory")


@router.get("/room-types", tags=["Room-Type Inventory"])
async def get_room_type_inventory(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    room_type: str | None = Query(None, description="Filter by room type"),
    tenant_id: str | None = Query(None, description="Tenant ID (auto-detected if omitted)"),
):
    """
    Get room-type inventory for a specific date.

    Returns sellable count per room type, broken down by lock category.
    If materialized view is empty, computes on-the-fly.
    """
    # Validate date format
    try:
        datetime.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Auto-detect tenant
    if not tenant_id:
        tenant = await db.organizations.find_one({}, {"_id": 0, "id": 1})
        if not tenant:
            room = await db.rooms.find_one({}, {"_id": 0, "tenant_id": 1})
            tenant_id = room.get("tenant_id") if room else None
        else:
            tenant_id = tenant.get("id")

    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    from core.room_type_inventory_service import get_room_type_inventory as get_inv
    results = await get_inv(tenant_id, date, room_type)

    total_physical = sum(r.get("physical_total", 0) for r in results)
    total_sellable = sum(r.get("sellable", 0) for r in results)
    total_locked = sum(
        r.get("locked_booking", 0) + r.get("locked_hold", 0) +
        r.get("locked_ooo", 0) + r.get("locked_oos", 0)
        for r in results
    )

    return {
        "date": date,
        "tenant_id": tenant_id,
        "room_types": results,
        "totals": {
            "physical": total_physical,
            "sellable": total_sellable,
            "locked": total_locked,
            "occupancy_pct": round((total_locked / total_physical) * 100, 1) if total_physical else 0,
        },
    }


@router.get("/room-types/summary", tags=["Room-Type Inventory"])
async def get_inventory_summary(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    tenant_id: str | None = Query(None, description="Tenant ID"),
):
    """Get aggregated inventory summary for a date range."""
    try:
        datetime.fromisoformat(start_date)
        datetime.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if not tenant_id:
        tenant = await db.organizations.find_one({}, {"_id": 0, "id": 1})
        if not tenant:
            room = await db.rooms.find_one({}, {"_id": 0, "tenant_id": 1})
            tenant_id = room.get("tenant_id") if room else None
        else:
            tenant_id = tenant.get("id")

    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    from core.room_type_inventory_service import get_inventory_summary as get_summary
    return await get_summary(tenant_id, start_date, end_date)


@router.post("/room-types/reconcile", tags=["Room-Type Inventory"])
async def trigger_reconciliation(
    start_date: str | None = Query(None, description="Start date (default: today)"),
    end_date: str | None = Query(None, description="End date (default: today + 30 days)"),
    tenant_id: str | None = Query(None, description="Tenant ID"),
    _perm=Depends(require_op("view_system_diagnostics")),  # v92.2 DW
):
    """
    Manually trigger inventory reconciliation.

    Recomputes room_type_inventory from room_night_locks for the date range.
    Reports any drift detected.
    """
    today = datetime.now(UTC).date()
    if not start_date:
        start_date = today.isoformat()
    if not end_date:
        end_date = (today + timedelta(days=30)).isoformat()

    try:
        datetime.fromisoformat(start_date)
        datetime.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if not tenant_id:
        tenant = await db.organizations.find_one({}, {"_id": 0, "id": 1})
        if not tenant:
            room = await db.rooms.find_one({}, {"_id": 0, "tenant_id": 1})
            tenant_id = room.get("tenant_id") if room else None
        else:
            tenant_id = tenant.get("id")

    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    from core.room_type_inventory_service import reconcile_date_range
    result = await reconcile_date_range(tenant_id, start_date, end_date)

    return {
        "status": "completed",
        "tenant_id": tenant_id,
        "date_range": {"start": start_date, "end": end_date},
        "dates_processed": result["dates_processed"],
        "types_processed": result["types_processed"],
        "drift_detected": result["drift_detected"],
        "drifts": result["drifts"],
    }


@router.get("/room-types/health", tags=["Room-Type Inventory"])
async def inventory_health(
    tenant_id: str | None = Query(None, description="Tenant ID"),
):
    """
    Quick health check: Does the materialized view exist and is it recent?
    """
    if not tenant_id:
        tenant = await db.organizations.find_one({}, {"_id": 0, "id": 1})
        if not tenant:
            room = await db.rooms.find_one({}, {"_id": 0, "tenant_id": 1})
            tenant_id = room.get("tenant_id") if room else None
        else:
            tenant_id = tenant.get("id")

    if not tenant_id:
        return {"status": "no_tenant", "healthy": False}

    today = datetime.now(UTC).date().isoformat()

    # Check if we have data for today
    count = await db.room_type_inventory.count_documents(
        {"tenant_id": tenant_id, "date": today}
    )

    # Check latest computation time
    latest = await db.room_type_inventory.find_one(
        {"tenant_id": tenant_id},
        {"_id": 0, "last_computed_at": 1},
        sort=[("last_computed_at", -1)],
    )

    freshness = "unknown"
    if latest and latest.get("last_computed_at"):
        try:
            last_dt = datetime.fromisoformat(latest["last_computed_at"])
            age_minutes = (datetime.now(UTC) - last_dt).total_seconds() / 60
            if age_minutes < 10:
                freshness = "fresh"
            elif age_minutes < 60:
                freshness = "recent"
            else:
                freshness = "stale"
        except (ValueError, TypeError):
            pass

    return {
        "tenant_id": tenant_id,
        "date": today,
        "room_types_today": count,
        "freshness": freshness,
        "last_computed_at": latest.get("last_computed_at") if latest else None,
        "healthy": count > 0 and freshness in ("fresh", "recent"),
    }
