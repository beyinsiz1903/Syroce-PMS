"""Idempotent PMS mutations for Exely reservation versions."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.database import db
from domains.channel_manager.providers.exely.lifecycle import (
    ACK_NOT_READY,
    ACK_PENDING,
    ACK_STALE,
    HOLD_MAPPING_REQUIRED,
    MALFORMED,
    PMS_DURABLE,
    PMS_FAILED,
    RECEIVED,
    acknowledge_durable_version,
    acknowledge_pending_versions,
    mark_version_state,
)

logger = logging.getLogger("exely.pms_lifecycle")

PMS_PROCESSING = "PMS_PROCESSING"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(kind: str, tenant_id: str, property_id: str, external_id: str, slot: int | None = None) -> str:
    parts = ("exely", kind, tenant_id, property_id, external_id, str(slot) if slot is not None else "")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "\x1f".join(parts)))


def _slot_external_id(external_id: str, slot: int) -> str:
    return f"{external_id}:room:{slot}"


async def _load_mapping(tenant_id: str, room: dict[str, Any]) -> dict[str, Any] | None:
    room_code = str(room.get("room_type_code") or "")
    rate_code = str(room.get("rate_plan_code") or "")
    if not room_code or not rate_code:
        return None
    mapping = await db.exely_room_mappings.find_one(
        {
            "tenant_id": tenant_id,
            "exely_room_code": room_code,
            "exely_rate_plan_code": rate_code,
        },
        {"_id": 0, "pms_room_type": 1},
    )
    if not mapping or not mapping.get("pms_room_type"):
        return None
    return mapping


def _assign_slots(
    previous_lineage: list[dict[str, Any]],
    rooms: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Match RoomStays to stable PMS slots, preserving IDs across index changes."""
    active_previous = [dict(row) for row in previous_lineage if row.get("active", True)]
    by_index = {str(row.get("index_number")): row for row in active_previous if str(row.get("index_number") or "")}
    used_slots: set[int] = set()
    assigned: list[dict[str, Any]] = []
    next_slot = max((int(row.get("slot_ordinal", -1)) for row in previous_lineage), default=-1) + 1

    for room in rooms:
        index_number = str(room.get("index_number") or "")
        lineage = by_index.get(index_number) if index_number else None
        if lineage and int(lineage["slot_ordinal"]) in used_slots:
            lineage = None
        if lineage is None:
            lineage = next(
                (row for row in sorted(active_previous, key=lambda item: int(item.get("slot_ordinal", 0))) if int(row.get("slot_ordinal", 0)) not in used_slots),
                None,
            )
        if lineage is None:
            slot = next_slot
            next_slot += 1
            lineage = {"slot_ordinal": slot}
        slot = int(lineage["slot_ordinal"])
        used_slots.add(slot)
        assigned.append({**lineage, "slot_ordinal": slot, "index_number": index_number, "active": True, "room": room})

    removed = [row for row in active_previous if int(row.get("slot_ordinal", 0)) not in used_slots]
    return assigned, removed


async def _ensure_guest(tenant_id: str, property_id: str, reservation: dict[str, Any]) -> str:
    guest_id = _stable_id("guest", tenant_id, property_id, reservation["external_id"])
    if await db.guests.find_one({"tenant_id": tenant_id, "id": guest_id}, {"_id": 0, "id": 1}):
        return guest_id

    guest_name = str(reservation.get("guest_name") or "")
    first_name = str(reservation.get("guest_firstname") or "") or (guest_name.split()[0] if guest_name else "Misafir")
    last_name = str(reservation.get("guest_lastname") or "") or (" ".join(guest_name.split()[1:]) if guest_name else "")
    guest = {
        "id": guest_id,
        "tenant_id": tenant_id,
        "first_name": first_name,
        "last_name": last_name,
        "name": guest_name or "Kanal Misafiri",
        "email": str(reservation.get("guest_email") or ""),
        "phone": str(reservation.get("guest_phone") or ""),
        "id_number": "",
        "nationality": str(reservation.get("guest_country") or ""),
        "vip_level": "none",
        "loyalty_tier": "none",
        "total_stays": 0,
        "notes": "Exely kanal rezervasyonu",
        "created_at": _now(),
    }
    from security.guest_write import encrypt_guest_insert

    try:
        await db.guests.insert_one(encrypt_guest_insert(guest))
    except DuplicateKeyError:
        if not await db.guests.find_one({"tenant_id": tenant_id, "id": guest_id}, {"_id": 0, "id": 1}):
            raise
    return guest_id


def _booking_fields(
    *,
    tenant_id: str,
    property_id: str,
    reservation: dict[str, Any],
    version_doc: dict[str, Any],
    room: dict[str, Any],
    mapping: dict[str, Any],
    slot: int,
    guest_id: str,
    booking_id: str,
) -> dict[str, Any]:
    check_in = str(room.get("check_in") or reservation.get("checkin_date") or "")
    check_out = str(room.get("check_out") or reservation.get("checkout_date") or "")
    try:
        nights = max((datetime.fromisoformat(check_out[:10]) - datetime.fromisoformat(check_in[:10])).days, 1)
    except (TypeError, ValueError):
        nights = max(int(reservation.get("nights") or 1), 1)
    room_total = float(room.get("amount") or 0)
    if room_total <= 0 and len(reservation.get("rooms") or []) == 1:
        room_total = float(reservation.get("total") or 0)
    adults = int(room.get("adults") or 1)
    children = int(room.get("children") or 0)
    external_id = str(reservation["external_id"])
    now = _now()
    return {
        "id": booking_id,
        "tenant_id": tenant_id,
        "property_id": property_id,
        "guest_id": guest_id,
        "guest_name": str(reservation.get("guest_name") or ""),
        "room_id": None,
        "room_number": None,
        "room_type": mapping["pms_room_type"],
        "check_in": check_in,
        "check_out": check_out,
        "adults": adults,
        "children": children,
        "children_ages": [],
        "guests_count": adults + children,
        "total_amount": room_total,
        "base_rate": room_total / nights,
        "paid_amount": 0.0,
        "status": "confirmed",
        "channel": "exely",
        "source_channel": "exely",
        "origin": "channel_import",
        "booking_source": "exely",
        "hold_status": "none",
        "allocation_source": "channel",
        "rate_plan": str(room.get("rate_plan_code") or ""),
        "special_requests": str(reservation.get("note") or ""),
        "group_booking_id": _stable_id("group", tenant_id, property_id, external_id),
        "company_id": None,
        "ota_channel": "exely",
        "ota_confirmation": external_id,
        "ota_reference_id": external_id,
        "external_reservation_id": _slot_external_id(external_id, slot),
        "provider_group_reservation_id": external_id,
        "provider_room_stay_index": str(room.get("index_number") or ""),
        "provider_version_key": version_doc["provider_version_key"],
        "source": {
            "provider": "exely",
            "external_reservation_id": _slot_external_id(external_id, slot),
            "group_external_reservation_id": external_id,
        },
        "created_at": now,
        "updated_at": now,
        "last_modified_by": "channel_manager",
    }


async def _upsert_booking(tenant_id: str, booking_doc: dict[str, Any]) -> str:
    booking_id = booking_doc["id"]
    existing = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {
            "_id": 0,
            "id": 1,
            "room_id": 1,
            "room_type": 1,
            "check_in": 1,
            "check_out": 1,
            "inventory_release_pending": 1,
        },
    )
    if not existing:
        from core.atomic_booking import create_booking_atomic

        try:
            await create_booking_atomic(tenant_id=tenant_id, booking_doc=dict(booking_doc))
        except DuplicateKeyError:
            existing = await db.bookings.find_one(
                {"tenant_id": tenant_id, "id": booking_id},
                {
                    "_id": 0,
                    "id": 1,
                    "room_id": 1,
                    "room_type": 1,
                    "check_in": 1,
                    "check_out": 1,
                    "inventory_release_pending": 1,
                },
            )
            if not existing:
                raise
        else:
            return "created"

    update_fields = dict(booking_doc)
    update_fields.pop("id", None)
    update_fields.pop("tenant_id", None)
    update_fields.pop("created_at", None)
    assignment_changed = bool(
        existing
        and existing.get("room_id")
        and (existing.get("room_type") != booking_doc["room_type"] or existing.get("check_in") != booking_doc["check_in"] or existing.get("check_out") != booking_doc["check_out"])
    )
    if existing and existing.get("room_id") and not assignment_changed:
        update_fields.pop("room_id", None)
        update_fields.pop("room_number", None)
    release_needed = assignment_changed or bool(existing and existing.get("inventory_release_pending"))
    if release_needed:
        update_fields["inventory_release_pending"] = True
    await db.bookings.update_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {"$set": update_fields},
    )
    if release_needed:
        from core.atomic_booking import release_booking_nights

        await release_booking_nights(tenant_id, booking_id, reason="channel_modified")
        await db.bookings.update_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"$unset": {"inventory_release_pending": ""}},
        )
    return "updated"


async def _cancel_booking(tenant_id: str, booking_id: str, version_key: str) -> bool:
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {"_id": 0, "id": 1, "status": 1, "provider_version_key": 1, "inventory_release_pending": 1},
    )
    if not booking:
        return False
    if booking.get("status") != "cancelled" or booking.get("provider_version_key") != version_key:
        await db.bookings.update_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": _now(),
                    "cancelled_by": "channel_manager",
                    "provider_version_key": version_key,
                    "inventory_release_pending": True,
                    "updated_at": _now(),
                }
            },
        )
    if booking.get("inventory_release_pending") or booking.get("status") != "cancelled" or booking.get("provider_version_key") != version_key:
        from core.atomic_booking import release_booking_nights

        await release_booking_nights(tenant_id, booking_id, reason="channel_cancelled")
        await db.bookings.update_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"$unset": {"inventory_release_pending": ""}},
        )
    return True


async def _readback_expectations(tenant_id: str, version_key: str, expectations: list[dict[str, Any]]) -> bool:
    if not expectations:
        return False
    for expected in expectations:
        booking = await db.bookings.find_one(
            {"tenant_id": tenant_id, "id": expected["pms_booking_id"]},
            {"_id": 0, "status": 1, "provider_version_key": 1, "inventory_release_pending": 1},
        )
        if not booking:
            return False
        if booking.get("status") != expected["status"]:
            return False
        if booking.get("provider_version_key") != version_key:
            return False
        if booking.get("inventory_release_pending"):
            return False
    return True


async def process_reservation_version(tenant_id: str, reservation: dict[str, Any]) -> dict[str, Any]:
    """Apply one current Exely version to PMS without contacting Exely."""
    identity = str(reservation.get("provider_version_identity") or "")
    if not identity:
        return {"success": False, "reason": "VERSION_IDENTITY_MISSING", "provider_write_count": 0}
    version_doc = await db.exely_reservation_versions.find_one({"version_identity": identity}, {"_id": 0})
    if not version_doc:
        return {"success": False, "reason": "VERSION_NOT_FOUND", "provider_write_count": 0}
    state = version_doc.get("processing_state")
    if state == PMS_DURABLE:
        durable = await _readback_expectations(tenant_id, version_doc["provider_version_key"], version_doc.get("durable_expectations") or [])
        return {
            "success": durable,
            "reason": "ALREADY_DURABLE" if durable else "PMS_READBACK_FAILED",
            "pms_booking_id": next(
                (row["pms_booking_id"] for row in version_doc.get("ack_confirmations") or []),
                None,
            ),
            "pms_booking_ids": [row["pms_booking_id"] for row in version_doc.get("ack_confirmations") or []],
            "provider_write_count": 0,
        }
    if state == MALFORMED:
        return {"success": False, "reason": state, "provider_write_count": 0}
    if state == HOLD_MAPPING_REQUIRED:
        rooms = list(version_doc.get("room_stays") or [])
        mappings_ready = bool(rooms)
        for room in rooms:
            if not await _load_mapping(tenant_id, room):
                mappings_ready = False
                break
        if not mappings_ready:
            return {"success": False, "reason": state, "provider_write_count": 0}
        await mark_version_state(identity, processing_state=RECEIVED, mapping_state="MAPPED")
        state = RECEIVED
    if state not in {RECEIVED, PMS_FAILED}:
        return {"success": False, "reason": "VERSION_NOT_CLAIMABLE", "provider_write_count": 0}

    claim = await db.exely_reservation_versions.update_one(
        {"version_identity": identity, "processing_state": {"$in": [RECEIVED, PMS_FAILED]}},
        {"$set": {"processing_state": PMS_PROCESSING, "processing_started_at": _now()}},
    )
    if getattr(claim, "modified_count", 0) != 1:
        return {"success": False, "reason": "VERSION_NOT_CLAIMABLE", "provider_write_count": 0}

    current = await db.exely_reservations.find_one(
        {"tenant_id": tenant_id, "provider_version_identity": identity},
        {"_id": 0},
    )
    if not current:
        await mark_version_state(identity, processing_state=PMS_FAILED, failure_code="CURRENT_VERSION_CHANGED")
        return {"success": False, "reason": "CURRENT_VERSION_CHANGED", "provider_write_count": 0}

    property_id = str(current.get("property_id") or "")
    external_id = str(current.get("external_id") or "")
    previous_lineage = list(current.get("room_stay_lineage") or [])
    expectations: list[dict[str, Any]] = []
    confirmations: list[dict[str, Any]] = []
    created = 0
    updated = 0
    cancelled = 0

    try:
        if version_doc.get("event_type") == "cancellation" or current.get("state") == "cancelled":
            active = [row for row in previous_lineage if row.get("active", True) and row.get("pms_booking_id")]
            if not active:
                raise RuntimeError("NO_DURABLE_PMS_BOOKING_FOR_CANCELLATION")
            cancel_assignments, _ = _assign_slots(previous_lineage, list(current.get("rooms") or []))
            cancel_index_by_slot = {int(row["slot_ordinal"]): str(row["room"].get("index_number") or "") for row in cancel_assignments}
            new_lineage = []
            for row in previous_lineage:
                item = dict(row)
                booking_id = str(item.get("pms_booking_id") or "")
                if item.get("active", True) and booking_id:
                    if not await _cancel_booking(tenant_id, booking_id, version_doc["provider_version_key"]):
                        raise RuntimeError("PMS_BOOKING_NOT_FOUND")
                    cancelled += 1
                    item["active"] = False
                    expectations.append({"pms_booking_id": booking_id, "status": "cancelled"})
                    confirmations.append(
                        {
                            "pms_booking_id": booking_id,
                            "room_stay_indexes": [cancel_index_by_slot.get(int(item.get("slot_ordinal", 0)), "")],
                        }
                    )
                new_lineage.append(item)
            pms_status = "cancellation_done"
        else:
            rooms = list(current.get("rooms") or [])
            if not rooms:
                raise RuntimeError("ROOM_STAYS_MISSING")
            if len(rooms) > 1 and any(not str(room.get("index_number") or "") for room in rooms):
                raise RuntimeError("ROOM_STAY_INDEX_MISSING")
            indexes = [str(room.get("index_number") or "") for room in rooms if str(room.get("index_number") or "")]
            if len(indexes) != len(set(indexes)):
                raise RuntimeError("ROOM_STAY_INDEX_DUPLICATE")
            mappings = []
            for room in rooms:
                mapping = await _load_mapping(tenant_id, room)
                if not mapping:
                    raise RuntimeError("ROOM_RATE_MAPPING_MISSING")
                mappings.append(mapping)

            guest_id = await _ensure_guest(tenant_id, property_id, current)
            assigned, removed = _assign_slots(previous_lineage, rooms)
            assigned_slots = {int(row["slot_ordinal"]) for row in assigned}
            new_lineage = [{**row, "active": False} for row in previous_lineage if int(row.get("slot_ordinal", 0)) not in assigned_slots]
            for row, mapping in zip(assigned, mappings, strict=True):
                slot = int(row["slot_ordinal"])
                booking_id = str(row.get("pms_booking_id") or _stable_id("booking", tenant_id, property_id, external_id, slot))
                booking_doc = _booking_fields(
                    tenant_id=tenant_id,
                    property_id=property_id,
                    reservation=current,
                    version_doc=version_doc,
                    room=row["room"],
                    mapping=mapping,
                    slot=slot,
                    guest_id=guest_id,
                    booking_id=booking_id,
                )
                action = await _upsert_booking(tenant_id, booking_doc)
                created += action == "created"
                updated += action == "updated"
                index_number = str(row["room"].get("index_number") or "")
                new_lineage.append(
                    {
                        "slot_ordinal": slot,
                        "slot_key": f"room:{slot}",
                        "pms_booking_id": booking_id,
                        "index_number": index_number,
                        "active": True,
                    }
                )
                expectations.append({"pms_booking_id": booking_id, "status": "confirmed"})
                confirmations.append({"pms_booking_id": booking_id, "room_stay_indexes": [index_number]})

            for row in removed:
                booking_id = str(row.get("pms_booking_id") or "")
                if not booking_id or not await _cancel_booking(tenant_id, booking_id, version_doc["provider_version_key"]):
                    raise RuntimeError("PMS_BOOKING_NOT_FOUND")
                cancelled += 1
                expectations.append({"pms_booking_id": booking_id, "status": "cancelled"})
            pms_status = "imported"

        if not await _readback_expectations(tenant_id, version_doc["provider_version_key"], expectations):
            raise RuntimeError("PMS_READBACK_FAILED")

        for confirmation in confirmations:
            booking = await db.bookings.find_one(
                {"tenant_id": tenant_id, "id": confirmation["pms_booking_id"]},
                {"_id": 0, "created_at": 1},
            )
            if not booking or not booking.get("created_at"):
                raise RuntimeError("PMS_READBACK_FAILED")
            confirmation["pms_created_at"] = booking["created_at"]

        if current.get("hold_booking_id"):
            from domains.channel_manager.providers.unmatched_hold import release_unmatched_reservation_hold

            release = await release_unmatched_reservation_hold(
                tenant_id=tenant_id,
                external_id=external_id,
                reason="mapping_resolved",
                delete_hold=True,
            )
            if not release.get("released"):
                raise RuntimeError("HOLD_RELEASE_FAILED")

        persisted = await db.exely_reservations.update_one(
            {"tenant_id": tenant_id, "provider_version_identity": identity},
            {
                "$set": {
                    "pms_status": pms_status,
                    "pms_booking_id": confirmations[0]["pms_booking_id"],
                    "pms_booking_ids": [row["pms_booking_id"] for row in confirmations],
                    "room_stay_lineage": sorted(new_lineage, key=lambda row: int(row.get("slot_ordinal", 0))),
                    "durable_version_key": version_doc["provider_version_key"],
                    "delivery_state": ACK_PENDING,
                    "delivery_confirmed": False,
                    "updated_at": _now(),
                },
                "$unset": {"hold_booking_id": ""},
            },
        )
        if getattr(persisted, "modified_count", 0) != 1:
            await mark_version_state(identity, processing_state=PMS_FAILED, ack_state=ACK_STALE, failure_code="CURRENT_VERSION_CHANGED")
            return {"success": False, "reason": "CURRENT_VERSION_CHANGED", "provider_write_count": 0}

        await mark_version_state(
            identity,
            processing_state=PMS_DURABLE,
            ack_state=ACK_PENDING,
            ack_confirmations=confirmations,
            durable_expectations=expectations,
            failure_code=None,
            pms_durable_at=_now(),
        )
        logger.info(
            "[EXELY-LIFECYCLE] pms_state=durable created=%d updated=%d cancelled=%d",
            created,
            updated,
            cancelled,
        )
        return {
            "success": True,
            "action": "cancelled" if pms_status == "cancellation_done" else ("updated" if updated else "created"),
            "pms_booking_id": confirmations[0]["pms_booking_id"],
            "pms_booking_ids": [row["pms_booking_id"] for row in confirmations],
            "created": created,
            "updated": updated,
            "cancelled": cancelled,
            "provider_write_count": 0,
        }
    except Exception as exc:
        failure_code = (
            str(exc)
            if str(exc)
            in {
                "CURRENT_VERSION_CHANGED",
                "HOLD_RELEASE_FAILED",
                "NO_DURABLE_PMS_BOOKING_FOR_CANCELLATION",
                "PMS_BOOKING_NOT_FOUND",
                "PMS_READBACK_FAILED",
                "ROOM_RATE_MAPPING_MISSING",
                "ROOM_STAYS_MISSING",
                "ROOM_STAY_INDEX_MISSING",
                "ROOM_STAY_INDEX_DUPLICATE",
            }
            else type(exc).__name__
        )
        await mark_version_state(identity, processing_state=PMS_FAILED, ack_state=ACK_NOT_READY, failure_code=failure_code)
        logger.error("[EXELY-LIFECYCLE] pms_state=failed exception_class=%s", type(exc).__name__)
        return {"success": False, "reason": failure_code, "provider_write_count": 0}


async def process_pending_reservations(tenant_id: str, provider=None, limit: int = 100) -> dict[str, Any]:
    reservations = await db.exely_reservations.find(
        {
            "tenant_id": tenant_id,
            "pms_status": {"$in": ["pending", "updated", "pending_mapping", "cancellation_pending"]},
        },
        {"_id": 0},
    ).to_list(limit)
    imported = 0
    updated = 0
    cancelled = 0
    errors: list[dict[str, str]] = []
    for reservation in reservations:
        result = await process_reservation_version(tenant_id, reservation)
        if result.get("success"):
            imported += int(result.get("created", 0) > 0)
            updated += int(result.get("updated", 0) > 0)
            cancelled += int(result.get("cancelled", 0) > 0)
        else:
            errors.append({"reason": str(result.get("reason") or "PMS_FAILED")})

    ack_result = {"acked": 0, "failed": 0, "provider_write_count": 0}
    if provider is not None:
        ack_result = await acknowledge_pending_versions(provider, tenant_id, limit=limit)
    return {
        "imported": imported,
        "updated": updated,
        "cancelled": cancelled,
        "total": len(reservations),
        "errors": errors,
        "acknowledgements": ack_result,
    }


async def process_single_and_ack(tenant_id: str, reservation: dict[str, Any], provider=None) -> dict[str, Any]:
    result = await process_reservation_version(tenant_id, reservation)
    if result.get("success") and provider is not None:
        current = await db.exely_reservations.find_one(
            {"tenant_id": tenant_id, "provider_version_identity": reservation.get("provider_version_identity")},
            {"_id": 0},
        )
        if current:
            acknowledgement = await acknowledge_durable_version(provider, current)
            result["acknowledgement"] = acknowledgement
            if not acknowledgement.get("success"):
                result["success"] = False
                result["reason"] = acknowledgement.get("reason", "ACK_FAILED")
        else:
            result["success"] = False
            result["reason"] = "CURRENT_VERSION_CHANGED"
    return result
