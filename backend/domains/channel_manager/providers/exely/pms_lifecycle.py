"""Idempotent PMS mutations for Exely reservation versions."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.database import db
from domains.channel_manager.providers.exely.lifecycle import (
    ACK_NOT_READY,
    ACK_PENDING,
    HOLD_MAPPING_REQUIRED,
    MALFORMED,
    PMS_DURABLE,
    PMS_FAILED,
    RECEIVED,
    _compare_versions,
    acknowledge_durable_version,
    acknowledge_pending_versions,
    mark_version_state,
)

logger = logging.getLogger("exely.pms_lifecycle")

PMS_PROCESSING = "PMS_PROCESSING"
PROCESSING_LEASE_SECONDS = max(int(os.getenv("EXELY_PROCESSING_LEASE_SECONDS", "60")), 10)
PROCESSING_HEARTBEAT_SECONDS = max(
    min(int(os.getenv("EXELY_PROCESSING_HEARTBEAT_SECONDS", "15")), PROCESSING_LEASE_SECONDS // 3),
    1,
)


class ProcessingClaimLostError(RuntimeError):
    """Raised when an Exely worker no longer owns its processing lease."""


@dataclass(frozen=True)
class ProcessingClaim:
    version_identity: str
    owner_token: str
    generation: int


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _result_matched(result: Any) -> int:
    matched = getattr(result, "matched_count", None)
    return int(matched if matched is not None else getattr(result, "modified_count", 0))


def _owned_claim_query(claim: ProcessingClaim, *, require_live: bool = True) -> dict[str, Any]:
    query: dict[str, Any] = {
        "version_identity": claim.version_identity,
        "processing_state": PMS_PROCESSING,
        "processing_owner_token": claim.owner_token,
        "processing_generation": claim.generation,
    }
    if require_live:
        query["processing_lease_expires_at"] = {"$gte": _utcnow().isoformat()}
    return query


async def _acquire_processing_claim(identity: str) -> ProcessingClaim | None:
    now = _utcnow()
    owner_token = uuid.uuid4().hex
    result = await db.exely_reservation_versions.update_one(
        {
            "version_identity": identity,
            "$or": [
                {"processing_state": {"$in": [RECEIVED, PMS_FAILED]}},
                {
                    "processing_state": PMS_PROCESSING,
                    "processing_lease_expires_at": {"$lt": now.isoformat()},
                },
            ],
        },
        {
            "$set": {
                "processing_state": PMS_PROCESSING,
                "processing_owner_token": owner_token,
                "processing_started_at": now.isoformat(),
                "processing_heartbeat_at": now.isoformat(),
                "processing_lease_expires_at": (now + timedelta(seconds=PROCESSING_LEASE_SECONDS)).isoformat(),
                "updated_at": now.isoformat(),
            },
            "$inc": {"processing_generation": 1},
        },
    )
    if _result_matched(result) != 1:
        return None
    owned = await db.exely_reservation_versions.find_one(
        {"version_identity": identity, "processing_owner_token": owner_token},
        {"_id": 0, "processing_generation": 1},
    )
    if not owned or not isinstance(owned.get("processing_generation"), int):
        return None
    return ProcessingClaim(identity, owner_token, int(owned["processing_generation"]))


async def _claim_is_owned(claim: ProcessingClaim) -> bool:
    owned = await db.exely_reservation_versions.find_one(
        _owned_claim_query(claim),
        {"_id": 0, "version_identity": 1},
    )
    return owned is not None


async def _require_processing_claim(claim: ProcessingClaim) -> None:
    if not await _claim_is_owned(claim):
        raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")


async def _renew_processing_claim(claim: ProcessingClaim) -> bool:
    now = _utcnow()
    result = await db.exely_reservation_versions.update_one(
        _owned_claim_query(claim),
        {
            "$set": {
                "processing_heartbeat_at": now.isoformat(),
                "processing_lease_expires_at": (now + timedelta(seconds=PROCESSING_LEASE_SECONDS)).isoformat(),
                "updated_at": now.isoformat(),
            }
        },
    )
    return _result_matched(result) == 1


async def _processing_claim_heartbeat(claim: ProcessingClaim, claim_lost: asyncio.Event) -> None:
    while True:
        await asyncio.sleep(PROCESSING_HEARTBEAT_SECONDS)
        try:
            if not await _renew_processing_claim(claim):
                claim_lost.set()
                logger.error("[EXELY-LIFECYCLE] processing_claim=lost")
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            claim_lost.set()
            logger.error(
                "[EXELY-LIFECYCLE] processing_claim=heartbeat_failed exception_class=%s",
                type(exc).__name__,
            )
            return


async def _run_claimed(mutation, claim: ProcessingClaim, claim_lost: asyncio.Event):
    if claim_lost.is_set() or not await _claim_is_owned(claim):
        if hasattr(mutation, "close"):
            mutation.close()
        raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")

    mutation_task = asyncio.ensure_future(mutation)
    lost_task = asyncio.create_task(claim_lost.wait())
    try:
        await asyncio.wait({mutation_task, lost_task}, return_when=asyncio.FIRST_COMPLETED)
        if claim_lost.is_set():
            mutation_task.cancel()
            with suppress(asyncio.CancelledError):
                await mutation_task
            raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")
        result = await mutation_task
        await _require_processing_claim(claim)
        return result
    finally:
        if not mutation_task.done():
            mutation_task.cancel()
            with suppress(asyncio.CancelledError):
                await mutation_task
        lost_task.cancel()
        with suppress(asyncio.CancelledError):
            await lost_task


async def _finish_processing_claim(claim: ProcessingClaim, **fields: Any) -> bool:
    fields["updated_at"] = _now()
    result = await db.exely_reservation_versions.update_one(
        _owned_claim_query(claim),
        {
            "$set": fields,
            "$unset": {
                "processing_owner_token": "",
                "processing_lease_expires_at": "",
                "processing_heartbeat_at": "",
            },
        },
    )
    return _result_matched(result) == 1


def _booking_fence_query(
    tenant_id: str,
    booking_id: str,
    claim: ProcessingClaim,
    existing_version_key: str | None,
    incoming_version_key: str,
) -> dict[str, Any]:
    query: dict[str, Any] = {
        "tenant_id": tenant_id,
        "id": booking_id,
    }
    if existing_version_key == incoming_version_key:
        query["$or"] = [
            {"exely_processing_generation": {"$exists": False}},
            {"exely_processing_generation": {"$lte": claim.generation}},
        ]
    if existing_version_key:
        query["provider_version_key"] = existing_version_key
    else:
        query["provider_version_key"] = {"$exists": False}
    return query


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
        "provider_room_stay_slot": slot,
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


async def _upsert_booking(
    tenant_id: str,
    booking_doc: dict[str, Any],
    claim: ProcessingClaim,
) -> str:
    booking_id = booking_doc["id"]
    booking_doc["exely_processing_generation"] = claim.generation
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
            "provider_version_key": 1,
            "exely_processing_generation": 1,
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
                    "provider_version_key": 1,
                    "exely_processing_generation": 1,
                },
            )
            if not existing:
                raise
        else:
            return "created"

    existing_version_key = str(existing.get("provider_version_key") or "") if existing else ""
    if existing_version_key and _compare_versions(booking_doc["provider_version_key"], existing_version_key) < 0:
        raise ProcessingClaimLostError("PROCESSING_CLAIM_STALE_VERSION")

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
    updated = await db.bookings.update_one(
        _booking_fence_query(
            tenant_id,
            booking_id,
            claim,
            existing_version_key or None,
            booking_doc["provider_version_key"],
        ),
        {"$set": update_fields},
    )
    if _result_matched(updated) != 1:
        raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")
    if release_needed:
        from core.atomic_booking import release_booking_nights

        await release_booking_nights(tenant_id, booking_id, reason="channel_modified")
        released = await db.bookings.update_one(
            {
                "tenant_id": tenant_id,
                "id": booking_id,
                "provider_version_key": booking_doc["provider_version_key"],
                "exely_processing_generation": claim.generation,
            },
            {"$unset": {"inventory_release_pending": ""}},
        )
        if _result_matched(released) != 1:
            raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")
    return "updated"


async def _cancel_booking(
    tenant_id: str,
    booking_id: str,
    version_key: str,
    claim: ProcessingClaim,
) -> bool:
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {
            "_id": 0,
            "id": 1,
            "status": 1,
            "provider_version_key": 1,
            "inventory_release_pending": 1,
            "exely_processing_generation": 1,
        },
    )
    if not booking:
        return False
    existing_version_key = str(booking.get("provider_version_key") or "")
    if existing_version_key and _compare_versions(version_key, existing_version_key) < 0:
        raise ProcessingClaimLostError("PROCESSING_CLAIM_STALE_VERSION")
    update_fields: dict[str, Any] = {"exely_processing_generation": claim.generation}
    cancellation_needed = booking.get("status") != "cancelled" or existing_version_key != version_key
    if cancellation_needed:
        update_fields.update(
            {
                "status": "cancelled",
                "cancelled_at": _now(),
                "cancelled_by": "channel_manager",
                "provider_version_key": version_key,
                "inventory_release_pending": True,
                "updated_at": _now(),
            }
        )
    fenced = await db.bookings.update_one(
        _booking_fence_query(
            tenant_id,
            booking_id,
            claim,
            existing_version_key or None,
            version_key,
        ),
        {"$set": update_fields},
    )
    if _result_matched(fenced) != 1:
        raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")
    if booking.get("inventory_release_pending") or booking.get("status") != "cancelled" or booking.get("provider_version_key") != version_key:
        from core.atomic_booking import release_booking_nights

        await release_booking_nights(tenant_id, booking_id, reason="channel_cancelled")
        released = await db.bookings.update_one(
            {
                "tenant_id": tenant_id,
                "id": booking_id,
                "provider_version_key": version_key,
                "exely_processing_generation": claim.generation,
            },
            {"$unset": {"inventory_release_pending": ""}},
        )
        if _result_matched(released) != 1:
            raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")
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
    if state not in {RECEIVED, PMS_FAILED, PMS_PROCESSING}:
        return {"success": False, "reason": "VERSION_NOT_CLAIMABLE", "provider_write_count": 0}

    claim = await _acquire_processing_claim(identity)
    if claim is None:
        return {"success": False, "reason": "VERSION_NOT_CLAIMABLE", "provider_write_count": 0}

    claim_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(_processing_claim_heartbeat(claim, claim_lost))
    expectations: list[dict[str, Any]] = []
    confirmations: list[dict[str, Any]] = []
    created = 0
    updated = 0
    cancelled = 0

    try:
        current = await db.exely_reservations.find_one(
            {"tenant_id": tenant_id, "provider_version_identity": identity},
            {"_id": 0},
        )
        await _require_processing_claim(claim)
        if not current:
            raise RuntimeError("CURRENT_VERSION_CHANGED")

        property_id = str(current.get("property_id") or "")
        external_id = str(current.get("external_id") or "")
        previous_lineage = list(current.get("room_stay_lineage") or [])
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
                    cancelled_booking = await _run_claimed(
                        _cancel_booking(
                            tenant_id,
                            booking_id,
                            version_doc["provider_version_key"],
                            claim,
                        ),
                        claim,
                        claim_lost,
                    )
                    if not cancelled_booking:
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

            guest_id = await _run_claimed(
                _ensure_guest(tenant_id, property_id, current),
                claim,
                claim_lost,
            )
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
                action = await _run_claimed(
                    _upsert_booking(tenant_id, booking_doc, claim),
                    claim,
                    claim_lost,
                )
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
                cancelled_booking = (
                    await _run_claimed(
                        _cancel_booking(
                            tenant_id,
                            booking_id,
                            version_doc["provider_version_key"],
                            claim,
                        ),
                        claim,
                        claim_lost,
                    )
                    if booking_id
                    else False
                )
                if not cancelled_booking:
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

            release = await _run_claimed(
                release_unmatched_reservation_hold(
                    tenant_id=tenant_id,
                    external_id=external_id,
                    reason="mapping_resolved",
                    delete_hold=True,
                ),
                claim,
                claim_lost,
            )
            if not release.get("released"):
                raise RuntimeError("HOLD_RELEASE_FAILED")

        persisted = await _run_claimed(
            db.exely_reservations.update_one(
                {
                    "tenant_id": tenant_id,
                    "provider_version_identity": identity,
                    "$or": [
                        {"processing_generation": {"$exists": False}},
                        {"processing_generation": {"$lte": claim.generation}},
                    ],
                },
                {
                    "$set": {
                        "pms_status": pms_status,
                        "pms_booking_id": confirmations[0]["pms_booking_id"],
                        "pms_booking_ids": [row["pms_booking_id"] for row in confirmations],
                        "room_stay_lineage": sorted(new_lineage, key=lambda row: int(row.get("slot_ordinal", 0))),
                        "durable_version_key": version_doc["provider_version_key"],
                        "delivery_state": ACK_PENDING,
                        "delivery_confirmed": False,
                        "processing_generation": claim.generation,
                        "updated_at": _now(),
                    },
                    "$unset": {"hold_booking_id": ""},
                },
            ),
            claim,
            claim_lost,
        )
        if _result_matched(persisted) != 1:
            raise RuntimeError("CURRENT_VERSION_CHANGED")

        if claim_lost.is_set():
            raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")
        finished = await _finish_processing_claim(
            claim,
            processing_state=PMS_DURABLE,
            ack_state=ACK_PENDING,
            ack_confirmations=confirmations,
            durable_expectations=expectations,
            failure_code=None,
            pms_durable_at=_now(),
        )
        if not finished:
            raise ProcessingClaimLostError("PROCESSING_CLAIM_LOST")
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
    except ProcessingClaimLostError:
        logger.error("[EXELY-LIFECYCLE] pms_state=failed failure_code=PROCESSING_CLAIM_LOST")
        return {"success": False, "reason": "PROCESSING_CLAIM_LOST", "provider_write_count": 0}
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
        failed = await _finish_processing_claim(
            claim,
            processing_state=PMS_FAILED,
            ack_state=ACK_NOT_READY,
            failure_code=failure_code,
        )
        if not failed:
            failure_code = "PROCESSING_CLAIM_LOST"
        logger.error("[EXELY-LIFECYCLE] pms_state=failed exception_class=%s", type(exc).__name__)
        return {"success": False, "reason": failure_code, "provider_write_count": 0}
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task


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
