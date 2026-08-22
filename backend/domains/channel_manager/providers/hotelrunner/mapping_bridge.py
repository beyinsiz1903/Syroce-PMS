"""Keep legacy HotelRunner mappings aligned with the canonical import model.

The HotelRunner setup UI historically wrote ``hotelrunner_room_mappings``
while the durable reservation import pipeline reads ``room_mappings`` and
``rate_plan_mappings``.  These helpers bridge both models without calling the
provider and make existing mappings usable during a cut-over.
"""

import uuid
from datetime import UTC, datetime

from core.database import db


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _property_id(tenant_id: str) -> str:
    # The legacy HotelRunner normalizer resolves payloads without an explicit
    # property to ``prop-001``. Use the same identity so the bridge and import
    # query cannot silently diverge. Explicit mapping property IDs still win.
    return "prop-001"


async def _canonical_room_type(tenant_id: str, requested: str) -> str:
    """Return the actual PMS room type spelling for a legacy mapping value."""
    requested = (requested or "").strip()
    if not requested:
        return ""
    room_types = await db.rooms.distinct("room_type", {"tenant_id": tenant_id, "is_active": {"$ne": False}})
    wanted = requested.casefold()
    return next((str(value) for value in room_types if str(value).strip().casefold() == wanted), requested)


async def mirror_hotelrunner_mapping(tenant_id: str, mapping: dict) -> None:
    """Upsert one legacy mapping into the canonical room/rate mapping tables."""
    room_code = str(mapping.get("hr_inv_code") or "").strip()
    if not room_code:
        return

    property_id = mapping.get("property_id") or await _property_id(tenant_id)
    room_type = await _canonical_room_type(
        tenant_id,
        mapping.get("pms_room_type_name") or mapping.get("pms_room_type") or "",
    )
    if not room_type:
        return

    room_query = {
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": "hotelrunner",
        "provider_room_code": room_code,
    }
    existing_room = await db.room_mappings.find_one(room_query, {"_id": 0, "id": 1, "created_at": 1})
    await db.room_mappings.update_one(
        room_query,
        {
            "$set": {
                **room_query,
                "pms_room_type_id": room_type,
                "pms_room_type_name": room_type,
                "provider_room_id": room_code,
                "is_active": True,
                "validation_status": "valid",
                "updated_at": _now(),
            },
            "$setOnInsert": {
                "id": (existing_room or {}).get("id") or str(uuid.uuid4()),
                "created_at": (existing_room or {}).get("created_at") or _now(),
            },
        },
        upsert=True,
    )

    rate_code = str(mapping.get("hr_rate_code") or "").strip()
    if not rate_code:
        return
    rate_query = {
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": "hotelrunner",
        "provider_rate_code": rate_code,
    }
    existing_rate = await db.rate_plan_mappings.find_one(rate_query, {"_id": 0, "id": 1, "created_at": 1})
    await db.rate_plan_mappings.update_one(
        rate_query,
        {
            "$set": {
                **rate_query,
                # HotelRunner's rate code is a stable local identity until a
                # dedicated PMS rate-plan is selected in a later workflow.
                "pms_rate_plan_id": rate_code,
                "pms_rate_plan_name": mapping.get("hr_room_name") or rate_code,
                "provider_rate_id": rate_code,
                "is_active": True,
                "validation_status": "valid",
                "updated_at": _now(),
            },
            "$setOnInsert": {
                "id": (existing_rate or {}).get("id") or str(uuid.uuid4()),
                "created_at": (existing_rate or {}).get("created_at") or _now(),
            },
        },
        upsert=True,
    )


async def backfill_hotelrunner_mappings(tenant_id: str) -> int:
    """Mirror every active legacy HotelRunner mapping for a tenant."""
    mappings = await db.hotelrunner_room_mappings.find(
        {"tenant_id": tenant_id},
        {"_id": 0},
    ).to_list(500)
    for mapping in mappings:
        await mirror_hotelrunner_mapping(tenant_id, mapping)
    return len(mappings)


async def remove_mirrored_mapping(tenant_id: str, mapping: dict) -> None:
    """Remove canonical rows only when no other legacy row still uses them."""
    room_code = str(mapping.get("hr_inv_code") or "").strip()
    rate_code = str(mapping.get("hr_rate_code") or "").strip()
    property_id = mapping.get("property_id") or await _property_id(tenant_id)

    if room_code and not await db.hotelrunner_room_mappings.find_one(
        {"tenant_id": tenant_id, "hr_inv_code": room_code}
    ):
        await db.room_mappings.delete_many(
            {
                "tenant_id": tenant_id,
                "property_id": property_id,
                "provider": "hotelrunner",
                "provider_room_code": room_code,
            }
        )
    if rate_code and not await db.hotelrunner_room_mappings.find_one(
        {"tenant_id": tenant_id, "hr_rate_code": rate_code}
    ):
        await db.rate_plan_mappings.delete_many(
            {
                "tenant_id": tenant_id,
                "property_id": property_id,
                "provider": "hotelrunner",
                "provider_rate_code": rate_code,
            }
        )
