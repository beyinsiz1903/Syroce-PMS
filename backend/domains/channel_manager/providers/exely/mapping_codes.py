"""Resolve Exely room/rate identifiers and their optional PMSConnect API keys."""

from typing import Any


def inbound_mapping_query(tenant_id: str, room_code: str, rate_code: str) -> dict[str, Any]:
    """Accept the configured ARI IDs or Exely's distinct PMS API codes on pulls."""
    return {
        "tenant_id": tenant_id,
        "$or": [
            {room_field: room_code, rate_field: rate_code}
            for room_field in ("exely_room_code", "pms_api_room_code")
            for rate_field in ("exely_rate_plan_code", "pms_api_rate_plan_code")
        ],
    }
