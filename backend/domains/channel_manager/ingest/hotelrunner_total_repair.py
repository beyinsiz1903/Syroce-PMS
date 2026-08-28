"""Repair legacy HotelRunner net totals from the immutable local event store.

This migration performs no provider I/O.  It is intentionally independent of
the HotelRunner reservation-read gate so historical imports can be corrected
while production reservation polling remains disabled.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from domains.channel_manager.ingest.hotelrunner_pricing import (
    hotelrunner_guest_total,
    matches_legacy_before_tax_total,
)

logger = logging.getLogger(__name__)


async def reconcile_hotelrunner_guest_totals_from_local_events(
    database: Any,
    *,
    max_events: int = 5000,
) -> int:
    """Repair exact legacy ``rooms[].price`` imports from stored raw events.

    The compare-and-set booking update makes the repair idempotent across
    multiple application replicas.  A booking is changed only when its current
    amount still exactly matches HotelRunner's before-tax ``price`` and the
    same stored payload contains a different guest-payable ``total``.  This
    deliberately excludes operator-adjusted amounts.
    """
    event_cursor = (
        database.raw_channel_events.find(
            {
                "provider": "hotelrunner",
                "external_reservation_id": {"$exists": True, "$ne": ""},
                "raw_payload": {"$type": "object"},
            },
            {
                "_id": 0,
                "tenant_id": 1,
                "external_reservation_id": 1,
                "raw_payload": 1,
                "received_at": 1,
            },
        )
        .sort("received_at", -1)
        .limit(max_events)
    )
    events = await event_cursor.to_list(max_events)

    latest_payloads: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        tenant_id = str(event.get("tenant_id") or "")
        external_id = str(event.get("external_reservation_id") or "")
        payload = event.get("raw_payload")
        key = (tenant_id, external_id)
        if tenant_id and external_id and isinstance(payload, dict) and key not in latest_payloads:
            latest_payloads[key] = payload

    if not latest_payloads:
        logger.info(
            "HotelRunner local gross-total reconciliation completed "
            "event_count=%d candidate_count=0 repaired_count=0",
            len(events),
        )
        return 0

    tenant_ids = sorted({tenant_id for tenant_id, _ in latest_payloads})
    external_ids = sorted({external_id for _, external_id in latest_payloads})
    booking_cursor = database.bookings.find(
        {
            "tenant_id": {"$in": tenant_ids},
            "external_reservation_id": {"$in": external_ids},
            "booking_source": "ota_import",
        },
        {
            "_id": 0,
            "id": 1,
            "tenant_id": 1,
            "external_reservation_id": 1,
            "total_amount": 1,
        },
    )

    repaired = 0
    async for booking in booking_cursor:
        tenant_id = str(booking.get("tenant_id") or "")
        external_id = str(booking.get("external_reservation_id") or "")
        payload = latest_payloads.get((tenant_id, external_id))
        current_total = booking.get("total_amount")
        if not payload or not matches_legacy_before_tax_total(current_total, payload):
            continue

        guest_total = hotelrunner_guest_total(payload)
        if guest_total is None:
            continue

        now = datetime.now(UTC).isoformat()
        result = await database.bookings.update_one(
            {
                "id": booking.get("id"),
                "tenant_id": tenant_id,
                "external_reservation_id": external_id,
                "booking_source": "ota_import",
                "total_amount": current_total,
            },
            {
                "$set": {
                    "total_amount": guest_total,
                    "provider_total_amount": guest_total,
                    "pricing_tax_inclusive": True,
                    "pricing_source": "channel_manager",
                    "hotelrunner_total_reconciled_from": float(current_total),
                    "hotelrunner_total_reconciled_at": now,
                    "hotelrunner_total_reconciliation_source": "local_raw_event",
                    "updated_at": now,
                }
            },
        )
        if not getattr(result, "modified_count", 0):
            continue

        repaired += 1
        await database.imported_reservations.update_one(
            {
                "tenant_id": tenant_id,
                "provider": "hotelrunner",
                "external_reservation_id": external_id,
            },
            {
                "$set": {
                    "total_amount": guest_total,
                    "updated_at": now,
                }
            },
        )

    logger.info(
        "HotelRunner local gross-total reconciliation completed "
        "event_count=%d candidate_count=%d repaired_count=%d",
        len(events),
        len(latest_payloads),
        repaired,
    )
    return repaired
