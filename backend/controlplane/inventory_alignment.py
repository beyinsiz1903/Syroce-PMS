"""
Inventory Alignment Service — Single Source of Truth Enforcement
=================================================================
Computes alignment status between:
  - room_type_inventory (authoritative, from room_night_locks)
  - channel manager sync snapshots (what providers actually have)

No fallback. If views are stale, state is reported as degraded.

Output: alignment_status, drift_count, drift_nights, provider breakdown.
Drift events are written to timeline for auditability.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import db

logger = logging.getLogger("controlplane.inventory_alignment")

STALE_THRESHOLD_MINUTES = 15


async def compute_inventory_alignment(
    tenant_id: Optional[str] = None,
    days_ahead: int = 14,
) -> Dict[str, Any]:
    """Compute inventory alignment across all connectors.

    Returns:
      alignment_status: aligned | drift_detected | stale | reconcile_running | no_data
      drift_count: total drift events
      drift_nights: total room-type-nights with drift
      provider_breakdown: per-provider drift details
      freshness: fresh | recent | stale | empty
    """
    # Auto-detect tenant
    if not tenant_id:
        tenant = await db.organizations.find_one({}, {"_id": 0, "id": 1})
        if not tenant:
            room = await db.rooms.find_one({}, {"_id": 0, "tenant_id": 1})
            tenant_id = room.get("tenant_id") if room else None
        else:
            tenant_id = tenant.get("id")

    if not tenant_id:
        return _empty_response("no_data", "No tenant found")

    today = datetime.now(timezone.utc).date()
    start_date = today.isoformat()
    end_date = (today + timedelta(days=days_ahead)).isoformat()

    # Step 1: Freshness check
    freshness = await _check_view_freshness(tenant_id, start_date)

    # Step 2: Get authoritative inventory from room_type_inventory
    inventory_docs = await db.room_type_inventory.find(
        {
            "tenant_id": tenant_id,
            "date": {"$gte": start_date, "$lte": end_date},
        },
        {"_id": 0},
    ).to_list(5000)

    if not inventory_docs:
        return _empty_response("no_data", "No inventory data in materialized view", freshness)

    # Build lookup: (room_type, date) → sellable
    inv_lookup: Dict[str, int] = {}
    for doc in inventory_docs:
        key = f"{doc.get('room_type')}_{doc.get('date')}"
        inv_lookup[key] = doc.get("sellable", 0)

    # Step 3: Get all active connectors for this tenant
    connectors = await db.cm_connectors.find(
        {"tenant_id": tenant_id, "status": "active"},
        {"_id": 0, "id": 1, "provider": 1, "property_id": 1},
    ).to_list(50)

    if not connectors:
        return {
            "alignment_status": "aligned" if freshness in ("fresh", "recent") else "stale",
            "freshness": freshness,
            "drift_count": 0,
            "drift_nights": 0,
            "provider_breakdown": [],
            "inventory_room_type_nights": len(inv_lookup),
            "connectors_checked": 0,
            "date_range": {"start": start_date, "end": end_date},
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "message": "No active connectors — inventory view is healthy but no channel sync to compare",
        }

    # Step 4: Compare against each connector's sync snapshots
    total_drift_count = 0
    total_drift_nights = 0
    provider_breakdown: List[Dict[str, Any]] = []

    for conn in connectors:
        conn_id = conn.get("id", "")
        provider = conn.get("provider", "unknown")

        # Get sync snapshots for this connector
        snapshots = await db.cm_sync_snapshots.find(
            {
                "tenant_id": tenant_id,
                "connector_id": conn_id,
                "date": {"$gte": start_date, "$lte": end_date},
            },
            {"_id": 0},
        ).to_list(5000)

        conn_drifts: List[Dict[str, Any]] = []
        checked = 0

        for snap in snapshots:
            rt = snap.get("room_type_id", "")
            date = snap.get("date", "")
            pushed_available = snap.get("available")
            if pushed_available is None:
                continue

            key = f"{rt}_{date}"
            authoritative = inv_lookup.get(key)
            if authoritative is None:
                continue

            checked += 1
            if pushed_available != authoritative:
                conn_drifts.append({
                    "room_type": rt,
                    "date": date,
                    "authoritative_sellable": authoritative,
                    "pushed_available": pushed_available,
                    "delta": authoritative - pushed_available,
                })

        drift_count = len(conn_drifts)
        total_drift_count += drift_count
        total_drift_nights += drift_count

        provider_breakdown.append({
            "connector_id": conn_id,
            "provider": provider,
            "snapshots_checked": checked,
            "drift_count": drift_count,
            "status": "aligned" if drift_count == 0 else "drift_detected",
            "drifts": conn_drifts[:20],
        })

    # Step 5: Determine overall status
    if freshness in ("stale", "empty"):
        alignment_status = "stale"
    elif total_drift_count > 0:
        alignment_status = "drift_detected"
    else:
        alignment_status = "aligned"

    # Step 6: Write drift events to timeline if any
    if total_drift_count > 0:
        await _write_drift_timeline_event(
            tenant_id, alignment_status, total_drift_count, provider_breakdown,
        )

    return {
        "alignment_status": alignment_status,
        "freshness": freshness,
        "drift_count": total_drift_count,
        "drift_nights": total_drift_nights,
        "provider_breakdown": provider_breakdown,
        "inventory_room_type_nights": len(inv_lookup),
        "connectors_checked": len(connectors),
        "date_range": {"start": start_date, "end": end_date},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


async def _check_view_freshness(tenant_id: str, date: str) -> str:
    """Check freshness of room_type_inventory materialized view."""
    latest = await db.room_type_inventory.find_one(
        {"tenant_id": tenant_id, "date": date},
        {"_id": 0, "last_computed_at": 1},
        sort=[("last_computed_at", -1)],
    )
    if not latest or not latest.get("last_computed_at"):
        return "empty"

    try:
        last_dt = datetime.fromisoformat(latest["last_computed_at"])
        age_minutes = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
        if age_minutes < 5:
            return "fresh"
        elif age_minutes < STALE_THRESHOLD_MINUTES:
            return "recent"
        else:
            return "stale"
    except (ValueError, TypeError):
        return "stale"


async def _write_drift_timeline_event(
    tenant_id: str,
    status: str,
    drift_count: int,
    provider_breakdown: List[Dict],
) -> None:
    """Write drift detection event to timeline for auditability."""
    try:
        from controlplane.timeline_writer import get_timeline_writer
        writer = get_timeline_writer()
        await writer.append(
            tenant_id=tenant_id,
            correlation_id=f"alignment-{datetime.now(timezone.utc).isoformat()}",
            entity_type="inventory_alignment",
            entity_id="ledger_alignment",
            stage="drift_detected",
            status="warning",
            source="inventory_alignment_check",
            metadata={
                "alignment_status": status,
                "total_drift_count": drift_count,
                "providers": [
                    {"provider": p["provider"], "drift_count": p["drift_count"]}
                    for p in provider_breakdown
                ],
            },
        )
    except Exception as e:
        logger.debug("Timeline drift event write failed: %s", e)


def _empty_response(status: str, message: str, freshness: str = "empty") -> Dict[str, Any]:
    return {
        "alignment_status": status,
        "freshness": freshness,
        "drift_count": 0,
        "drift_nights": 0,
        "provider_breakdown": [],
        "inventory_room_type_nights": 0,
        "connectors_checked": 0,
        "date_range": {"start": "", "end": ""},
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "message": message,
    }
