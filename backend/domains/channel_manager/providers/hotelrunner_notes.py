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
