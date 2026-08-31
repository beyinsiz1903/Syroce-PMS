"""HotelRunner reservation note extraction and PMS note synchronization."""

import uuid
from datetime import UTC, datetime
from typing import Any


def extract_hotelrunner_note(payload: dict[str, Any]) -> str:
    """Return the provider note and room comments as one de-duplicated note."""
    parts: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, dict):
            value = value.get("body") or value.get("content") or value.get("text")
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)

    add(payload.get("note"))
    for comment in payload.get("comments") or []:
        add(comment)
    for room in payload.get("rooms") or []:
        if not isinstance(room, dict):
            continue
        add(room.get("note"))
        for comment in room.get("comments") or []:
            add(comment)

    return "\n".join(parts)


def _provider_note_id(tenant_id: str, booking_id: str, external_reservation_id: str) -> str:
    identity = f"syroce:hotelrunner-note:{tenant_id}:{booking_id}:{external_reservation_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


async def resolve_legacy_hotelrunner_note(
    database,
    *,
    tenant_id: str,
    booking: dict[str, Any],
) -> dict[str, Any] | None:
    """Project an old HotelRunner import note into the existing Notes tab.

    Reservations imported before provider notes were synchronized can still
    carry the note in ``imported_reservations`` or ``reservation_lineage``.
    This read-only fallback keeps those notes visible without creating a
    second HotelRunner-specific UI or mutating historical reservations.
    """
    source = booking.get("source") if isinstance(booking.get("source"), dict) else {}
    provider = str(source.get("provider") or booking.get("provider") or "").strip().lower()
    if provider and provider != "hotelrunner":
        return None

    booking_id = str(booking.get("id") or "").strip()
    external_reservation_id = str(
        booking.get("external_reservation_id")
        or source.get("external_reservation_id")
        or ""
    ).strip()
    if not booking_id or not external_reservation_id:
        return None

    projection = {
        "_id": 0,
        "provider": 1,
        "provider_note": 1,
        "raw_payload": 1,
        "payload": 1,
        "provider_updated_at": 1,
        "provider_last_modified_at": 1,
        "received_at": 1,
        "updated_at": 1,
        "created_at": 1,
    }
    provider_record = None
    import_record_id = str(source.get("import_record_id") or "").strip()
    if import_record_id:
        provider_record = await database.imported_reservations.find_one(
            {"id": import_record_id, "tenant_id": tenant_id},
            projection,
        )
        if (
            provider_record
            and str(provider_record.get("provider") or "").strip().lower()
            != "hotelrunner"
        ):
            provider_record = None
    if not provider_record:
        provider_record = await database.imported_reservations.find_one(
            {
                "tenant_id": tenant_id,
                "provider": "hotelrunner",
                "external_reservation_id": external_reservation_id,
            },
            projection,
        )
    if not provider_record:
        provider_record = await database.reservation_lineage.find_one(
            {
                "tenant_id": tenant_id,
                "provider": "hotelrunner",
                "external_reservation_id": external_reservation_id,
            },
            projection,
        )

    note_source = provider_record or {}
    content = str(note_source.get("provider_note") or "").strip()
    if not content:
        stored_payload = note_source.get("raw_payload") or note_source.get("payload")
        if isinstance(stored_payload, dict):
            content = extract_hotelrunner_note(stored_payload)

    # The oldest imports did not persist ``provider_note`` into the canonical
    # mirrors. Their immutable raw event still contains the agency note. Keep
    # this lookup tenant/provider/external-id scoped so a similarly numbered
    # reservation from another connection can never leak into this booking.
    if not content:
        raw_events = getattr(database, "raw_channel_events", None)
        if raw_events is not None:
            raw_event = await raw_events.find_one(
                {
                    "tenant_id": tenant_id,
                    "provider": "hotelrunner",
                    "external_reservation_id": external_reservation_id,
                    "raw_payload": {"$type": "object"},
                },
                {
                    "_id": 0,
                    "raw_payload": 1,
                    "provider_timestamp": 1,
                    "received_at": 1,
                },
                sort=[("received_at", -1)],
            )
            if raw_event and isinstance(raw_event.get("raw_payload"), dict):
                content = extract_hotelrunner_note(raw_event["raw_payload"])
                note_source = raw_event

    if not content:
        legacy_events = getattr(database, "hotelrunner_raw_events", None)
        if legacy_events is not None:
            raw_event = await legacy_events.find_one(
                {
                    "tenant_id": tenant_id,
                    "provider": "hotelrunner",
                    "$or": [
                        {"hr_number": external_reservation_id},
                        {"external_id": external_reservation_id},
                    ],
                    "payload": {"$type": "object"},
                },
                {
                    "_id": 0,
                    "payload": 1,
                    "received_at": 1,
                },
                sort=[("received_at", -1)],
            )
            if raw_event and isinstance(raw_event.get("payload"), dict):
                content = extract_hotelrunner_note(raw_event["payload"])
                note_source = raw_event

    if not content and provider == "hotelrunner":
        content = str(booking.get("provider_note") or "").strip()
    if not content:
        return None

    created_at = (
        note_source.get("provider_updated_at")
        or note_source.get("provider_last_modified_at")
        or note_source.get("provider_timestamp")
        or note_source.get("received_at")
        or note_source.get("updated_at")
        or note_source.get("created_at")
        or booking.get("updated_at")
        or booking.get("created_at")
        or datetime.now(UTC).isoformat()
    )
    return {
        "id": _provider_note_id(tenant_id, booking_id, external_reservation_id),
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "note_type": "general",
        "content": content,
        "created_by": "HotelRunner / Acente",
        "created_at": created_at,
        "source": "hotelrunner",
        "external_reservation_id": external_reservation_id,
        "legacy_projection": True,
    }


async def sync_hotelrunner_note(
    database,
    *,
    tenant_id: str,
    booking_id: str,
    external_reservation_id: str,
    content: str,
    provider_updated_at: str = "",
    update_existing: bool = True,
) -> None:
    """Upsert HotelRunner's note into the existing reservation Notes tab.

    The deterministic id keeps retries idempotent. Only the provider-owned note
    is updated or removed; notes created by PMS users remain untouched.
    """
    note_id = _provider_note_id(tenant_id, booking_id, external_reservation_id)
    note_filter = {
        "id": note_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
    }
    normalized_content = str(content or "").strip()

    if not normalized_content:
        # Some HotelRunner list/pull shapes omit notes entirely. Treat an empty
        # projection as "not supplied" so a partial payload cannot erase the
        # provider note already visible in PMS.
        return

    now = datetime.now(UTC).isoformat()
    insert_fields = {
        "id": note_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "note_type": "general",
        "created_by": "HotelRunner",
        "created_at": now,
        "source": "hotelrunner",
        "external_reservation_id": external_reservation_id,
    }
    if update_existing:
        await database.reservation_notes.update_one(
            note_filter,
            {
                "$set": {
                    "content": normalized_content,
                    "updated_at": now,
                    "provider_updated_at": provider_updated_at,
                },
                "$setOnInsert": insert_fields,
            },
            upsert=True,
        )
        return

    await database.reservation_notes.update_one(
        note_filter,
        {
            "$setOnInsert": {
                **insert_fields,
                "content": normalized_content,
                "updated_at": now,
                "provider_updated_at": provider_updated_at,
            }
        },
        upsert=True,
    )
