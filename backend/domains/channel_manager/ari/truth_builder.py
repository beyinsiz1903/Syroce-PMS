from typing import Any

from domains.channel_manager.unified_rate_manager_router import get_unified_grid
from models.schemas import User


async def build_pms_ari_snapshot(
    tenant_id: str,
    property_id: str,
    provider: str,
    date_from: str,
    date_to: str,
) -> list[dict[str, Any]]:
    """
    Build the gold source of truth for ARI (Availability, Rates, Inventory)
    by unifying local rooms, bookings, room mappings, and rate calendars.

    This invokes the Unified Rate Manager's core grid builder to ensure
    100% parity with what the PMS expects the channel state to be.
    """
    # Create a dummy user object to satisfy the dependency injection of get_unified_grid
    # Since we only need tenant_id for the queries inside get_unified_grid.
    dummy_user = User(
        id="system_drift_worker",
        tenant_id=tenant_id,
        email="system@driftworker.local",
        name="System Drift Worker",
        role="super_admin",
        is_active=True,
    )

    grid_response = await get_unified_grid(
        start_date=date_from,
        end_date=date_to,
        provider=provider,
        current_user=dummy_user,
    )

    grid_data = grid_response.get("grid", [])

    pms_snapshot = []

    for row in grid_data:
        rt_code = row.get("room_type_code")
        rp_code = row.get("rate_plan_code")

        for date_entry in row.get("dates", []):
            snapshot_item = {
                "room_type_code": rt_code,
                "rate_plan_code": rp_code,
                "date": date_entry.get("date"),
                "availability": date_entry.get("availability"),
                "rate": date_entry.get("rate"),
                "min_stay": date_entry.get("min_stay", 1),
                "stop_sell": date_entry.get("stop_sell", False),
                # If there are nested restrictions in the future, they map here
                "restrictions": {
                    "min_stay": date_entry.get("min_stay", 1),
                    "stop_sell": date_entry.get("stop_sell", False),
                }
            }
            pms_snapshot.append(snapshot_item)

    return pms_snapshot
