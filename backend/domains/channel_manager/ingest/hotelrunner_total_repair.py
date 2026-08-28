"""Repair legacy HotelRunner net totals from local provider truth stores.

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
    """Repair exact legacy ``rooms[].price`` imports from stored provider data.

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
    payload_sources: dict[tuple[str, str], str] = {}
    linked_booking_keys: dict[tuple[str, str], tuple[str, str]] = {}
    imported_record_ids: dict[tuple[str, str], str] = {}

    def remember_payload(
        *,
        tenant_id: Any,
        external_id: Any,
        payload: Any,
        source: str,
    ) -> None:
        key = (str(tenant_id or ""), str(external_id or ""))
        if (
            key[0]
            and key[1]
            and isinstance(payload, dict)
            and payload
            and key not in latest_payloads
        ):
            latest_payloads[key] = payload
            payload_sources[key] = source

    for event in events:
        remember_payload(
            tenant_id=event.get("tenant_id"),
            external_id=event.get("external_reservation_id"),
            payload=event.get("raw_payload"),
            source="local_raw_event",
        )

    # Older/manual HotelRunner paths pre-date the unified event ledger. Their
    # payloads are still kept locally in the provider raw-event and reservation
    # mirrors. Reading these collections is required while reservation polling
    # is deliberately disabled in production; no provider request is made.
    legacy_event_cursor = (
        database.hotelrunner_raw_events.find(
            {
                "$or": [
                    {"hr_number": {"$exists": True, "$ne": ""}},
                    {"external_id": {"$exists": True, "$ne": ""}},
                ],
                "payload": {"$type": "object"},
            },
            {
                "_id": 0,
                "tenant_id": 1,
                "hr_number": 1,
                "external_id": 1,
                "payload": 1,
                "received_at": 1,
            },
        )
        .sort("received_at", -1)
        .limit(max_events)
    )
    legacy_events = await legacy_event_cursor.to_list(max_events)
    for event in legacy_events:
        remember_payload(
            tenant_id=event.get("tenant_id"),
            external_id=event.get("hr_number") or event.get("external_id"),
            payload=event.get("payload"),
            source="hotelrunner_raw_event",
        )

    mirror_cursor = (
        database.hotelrunner_reservations.find(
            {
                "$or": [
                    {"hr_number": {"$exists": True, "$ne": ""}},
                    {"external_id": {"$exists": True, "$ne": ""}},
                ]
            },
            {
                "_id": 0,
                "tenant_id": 1,
                "hr_number": 1,
                "external_id": 1,
                "pms_booking_id": 1,
                "raw_data": 1,
                "total": 1,
                "rooms": 1,
                "synced_at": 1,
            },
        )
        .sort("synced_at", -1)
        .limit(max_events)
    )
    mirrors = await mirror_cursor.to_list(max_events)
    for mirror in mirrors:
        external_id = mirror.get("hr_number") or mirror.get("external_id")
        payload = mirror.get("raw_data")
        if not isinstance(payload, dict) or not payload:
            payload = {
                "hr_number": external_id,
                "total": mirror.get("total"),
                "rooms": mirror.get("rooms") or [],
            }
        remember_payload(
            tenant_id=mirror.get("tenant_id"),
            external_id=external_id,
            payload=payload,
            source="hotelrunner_reservation_mirror",
        )
        tenant_id = str(mirror.get("tenant_id") or "")
        booking_id = str(mirror.get("pms_booking_id") or "")
        if tenant_id and booking_id and external_id:
            linked_booking_keys[(tenant_id, booking_id)] = (
                tenant_id,
                str(external_id),
            )

    imported_cursor = (
        database.imported_reservations.find(
            {
                "$or": [
                    {"provider": "hotelrunner"},
                    {"raw_payload.hr_number": {"$exists": True, "$ne": ""}},
                ],
                "external_reservation_id": {"$exists": True, "$ne": ""},
                "raw_payload": {"$type": "object"},
            },
            {
                "_id": 0,
                "id": 1,
                "tenant_id": 1,
                "external_reservation_id": 1,
                "pms_booking_id": 1,
                "raw_payload": 1,
                "updated_at": 1,
            },
        )
        .sort("updated_at", -1)
        .limit(max_events)
    )
    imported_payloads = await imported_cursor.to_list(max_events)
    for imported in imported_payloads:
        tenant_id = str(imported.get("tenant_id") or "")
        external_id = str(imported.get("external_reservation_id") or "")
        payload_key = (tenant_id, external_id)
        remember_payload(
            tenant_id=tenant_id,
            external_id=external_id,
            payload=imported.get("raw_payload"),
            source="imported_reservation_payload",
        )
        booking_id = str(imported.get("pms_booking_id") or "")
        if tenant_id and booking_id and external_id:
            linked_booking_keys[(tenant_id, booking_id)] = payload_key
        record_id = str(imported.get("id") or "")
        if record_id and payload_key not in imported_record_ids:
            imported_record_ids[payload_key] = record_id

    local_record_count = (
        len(events) + len(legacy_events) + len(mirrors) + len(imported_payloads)
    )

    if not latest_payloads:
        logger.info(
            "HotelRunner local gross-total reconciliation completed "
            "event_count=%d candidate_count=0 repaired_count=0",
            local_record_count,
        )
        return 0

    tenant_ids = sorted({tenant_id for tenant_id, _ in latest_payloads})
    external_ids = sorted({external_id for _, external_id in latest_payloads})
    linked_booking_ids = sorted({booking_id for _, booking_id in linked_booking_keys})
    booking_matchers: list[dict[str, Any]] = [
        {
            "tenant_id": {"$in": tenant_ids},
            "external_reservation_id": {"$in": external_ids},
        }
    ]
    if linked_booking_ids:
        booking_matchers.append(
            {
                "tenant_id": {"$in": tenant_ids},
                "id": {"$in": linked_booking_ids},
            }
        )
    booking_cursor = database.bookings.find(
        {"$or": booking_matchers},
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
        payload_key = (tenant_id, external_id)
        if payload_key not in latest_payloads:
            booking_id = str(booking.get("id") or "")
            payload_key = linked_booking_keys.get((tenant_id, booking_id), payload_key)
            external_id = payload_key[1]
        payload = latest_payloads.get(payload_key)
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
                    "hotelrunner_total_reconciliation_source": payload_sources[
                        payload_key
                    ],
                    "updated_at": now,
                }
            },
        )
        if not getattr(result, "modified_count", 0):
            continue

        repaired += 1
        imported_filter = {
            "tenant_id": tenant_id,
            "external_reservation_id": external_id,
        }
        if imported_record_ids.get(payload_key):
            imported_filter = {
                "tenant_id": tenant_id,
                "id": imported_record_ids[payload_key],
            }
        await database.imported_reservations.update_one(
            imported_filter,
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
        local_record_count,
        len(latest_payloads),
        repaired,
    )
    return repaired
