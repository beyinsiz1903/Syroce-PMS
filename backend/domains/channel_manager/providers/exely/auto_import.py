"""Exely reservation import compatibility facade.

All PMS mutations and provider acknowledgements are delegated to the durable,
per-version lifecycle. This module remains as the stable import surface used by
the scheduler and API router.
"""

from __future__ import annotations

from typing import Any

from core.database import db
from domains.channel_manager.providers.exely.pms_lifecycle import (
    process_pending_reservations,
    process_reservation_version,
)


async def auto_import_reservation(tenant_id: str, channel_res: dict[str, Any]) -> dict[str, Any]:
    """Apply the current provider version to PMS without sending an ACK."""
    return await process_reservation_version(tenant_id, channel_res)


async def auto_import_pending(tenant_id: str, provider=None) -> dict[str, Any]:
    """Apply pending versions, then ACK only versions proven durable."""
    return await process_pending_reservations(tenant_id, provider=provider)


async def process_pending_cancellations(tenant_id: str) -> int:
    """Durably process pending cancellations without contacting Exely."""
    pending = await db.exely_reservations.find(
        {"tenant_id": tenant_id, "pms_status": "cancellation_pending"},
        {"_id": 0},
    ).to_list(100)
    cancelled = 0
    for reservation in pending:
        result = await process_reservation_version(tenant_id, reservation)
        if result.get("success"):
            cancelled += int(result.get("cancelled", 0) > 0)
    return cancelled
