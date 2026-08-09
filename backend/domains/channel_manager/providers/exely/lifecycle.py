"""Durable per-version lifecycle and acknowledgement state for Exely pulls."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.database import db

logger = logging.getLogger("exely.lifecycle")

RECEIVED = "RECEIVED"
HOLD_MAPPING_REQUIRED = "HOLD_MAPPING_REQUIRED"
MALFORMED = "MALFORMED"
PMS_DURABLE = "PMS_DURABLE"
PMS_FAILED = "PMS_FAILED"

ACK_NOT_READY = "NOT_READY"
ACK_PENDING = "PENDING"
ACK_SENDING = "SENDING"
ACKED = "ACKED"
ACK_REJECTED = "REJECTED"
ACK_AMBIGUOUS = "AMBIGUOUS"
ACK_STALE = "STALE_VERSION"


def version_identity(tenant_id: str, property_id: str, reservation_id: str, version_key: str) -> str:
    material = "\x1f".join((tenant_id, property_id, reservation_id, version_key))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _provider_time(value: str) -> datetime:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("missing provider timestamp")
    parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _compare_versions(incoming: str, current: str) -> int:
    incoming_time = _provider_time(incoming)
    current_time = _provider_time(current)
    return (incoming_time > current_time) - (incoming_time < current_time)


async def _mapping_status(tenant_id: str, rooms: list[dict[str, Any]]) -> tuple[bool, str]:
    if not rooms:
        return False, "ROOM_STAYS_MISSING"
    if len(rooms) > 1 and any(not str(room.get("index_number") or "") for room in rooms):
        return False, "ROOM_STAY_INDEX_MISSING"
    indexes = [str(room.get("index_number") or "") for room in rooms if str(room.get("index_number") or "")]
    if len(indexes) != len(set(indexes)):
        return False, "ROOM_STAY_INDEX_DUPLICATE"
    for room in rooms:
        room_code = str(room.get("room_type_code") or "")
        rate_code = str(room.get("rate_plan_code") or "")
        if not room_code:
            return False, "ROOM_CODE_MISSING"
        if not rate_code:
            return False, "RATE_PLAN_CODE_MISSING"
        mapping = await db.exely_room_mappings.find_one(
            {
                "tenant_id": tenant_id,
                "exely_room_code": room_code,
                "exely_rate_plan_code": rate_code,
            },
            {"_id": 0, "pms_room_type": 1},
        )
        if not mapping or not mapping.get("pms_room_type"):
            return False, "ROOM_RATE_MAPPING_MISSING"
    return True, "MAPPED"


def _reservation_document(
    tenant_id: str,
    canonical: dict[str, Any],
    event_id: str,
    payload_hash: str,
    identity: str,
) -> dict[str, Any]:
    guest = canonical["guest"]
    stay = canonical["stay"]
    financial = canonical["financial"]
    now = datetime.now(UTC).isoformat()
    return {
        "tenant_id": tenant_id,
        "external_id": canonical["external_id"],
        "provider": "exely",
        "source_provider": "exely",
        "property_id": canonical["property_id"],
        "provider_reservation_id": canonical["provider_reservation_id"],
        "provider_reservation_id_context": canonical.get("provider_reservation_id_context", ""),
        "provider_event_id": event_id,
        "provider_version": canonical["provider_last_modified_at"],
        "provider_version_key": canonical["provider_last_modified_at"],
        "provider_version_identity": identity,
        "provider_created_at": canonical["provider_created_at"],
        "provider_last_modified_at": canonical["provider_last_modified_at"],
        "provider_payload_hash": payload_hash,
        "channel": canonical["channel"],
        "channel_display": canonical["channel_display"],
        "state": canonical["status"],
        "guest_name": guest["name"],
        "guest_firstname": guest["first_name"],
        "guest_lastname": guest["last_name"],
        "guest_email": guest["email"],
        "guest_phone": guest["phone"],
        "guest_country": guest["country"],
        "checkin_date": stay["check_in"],
        "checkout_date": stay["check_out"],
        "nights": stay["nights"],
        "total": financial["total_amount"],
        "currency": financial["currency"],
        "payment_method": financial["payment_method"],
        "total_rooms": canonical["total_rooms"],
        "total_guests": canonical["total_guests"],
        "rooms": canonical["rooms"],
        "note": canonical["notes"],
        "message_uid": canonical.get("message_uid", ""),
        "source_system": "EXELY",
        "ingested_via": canonical["ingested_via"],
        "external_write_protected": True,
        "synced_at": now,
        "raw_event_id": event_id,
        "confidence_score": None,
        "delivery_confirmed": False,
        "delivery_state": ACK_NOT_READY,
        "processing_generation": 0,
    }


async def persist_exely_event(
    tenant_id: str,
    canonical: dict[str, Any],
    event_type: str,
    event_id: str,
    payload_hash: str,
) -> dict[str, Any]:
    """Persist exactly one provider version without performing a PMS mutation."""
    external_id = str(canonical.get("external_id") or "")
    property_id = str(canonical.get("property_id") or "")
    version_key = str(canonical.get("provider_last_modified_at") or "")
    created_at = str(canonical.get("provider_created_at") or "")
    if not external_id or not property_id:
        return {"action": "error", "reason": "PROVIDER_IDENTITY_MISSING"}

    fallback_key = version_key or f"missing:{payload_hash}"
    identity = version_identity(tenant_id, property_id, external_id, fallback_key)
    try:
        _provider_time(version_key)
        _provider_time(created_at)
    except (TypeError, ValueError):
        await db.exely_reservation_versions.update_one(
            {"version_identity": identity},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "property_id": property_id,
                    "provider_reservation_id": external_id,
                    "version_identity": identity,
                    "provider_version_key": version_key,
                    "processing_state": MALFORMED,
                    "ack_state": ACK_NOT_READY,
                    "failure_code": "PROVIDER_TIMESTAMP_INVALID",
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(UTC).isoformat()},
            },
            upsert=True,
        )
        return {"action": "error", "reason": "PROVIDER_TIMESTAMP_INVALID"}

    current_query = {"tenant_id": tenant_id, "property_id": property_id, "external_id": external_id}
    current = await db.exely_reservations.find_one(
        current_query,
        {
            "_id": 0,
            "id": 1,
            "provider_version_key": 1,
            "provider_version_identity": 1,
            "provider_payload_hash": 1,
            "state": 1,
            "pms_booking_ids": 1,
            "pms_booking_id": 1,
        },
    )
    if not current:
        current = await db.exely_reservations.find_one(
            {"tenant_id": tenant_id, "external_id": external_id},
            {
                "_id": 0,
                "id": 1,
                "provider_version_key": 1,
                "provider_version_identity": 1,
                "provider_payload_hash": 1,
                "state": 1,
                "pms_booking_ids": 1,
                "pms_booking_id": 1,
            },
        )
        if current and current.get("id"):
            current_query = {"tenant_id": tenant_id, "id": current["id"]}
    if current and current.get("provider_version_key"):
        comparison = _compare_versions(version_key, current["provider_version_key"])
        if comparison < 0:
            return {"action": "skip", "reason": "stale_event", "external_id": external_id}
        if comparison == 0:
            if current.get("provider_payload_hash") == payload_hash:
                return {"action": "skip", "reason": "duplicate_payload", "external_id": external_id}
            return {"action": "error", "reason": "VERSION_PAYLOAD_CONFLICT", "external_id": external_id}

    is_cancellation = event_type == "cancellation" or canonical.get("status") == "cancelled"
    mapped, mapping_code = (True, "NOT_APPLICABLE") if is_cancellation else await _mapping_status(tenant_id, canonical["rooms"])
    processing_state = RECEIVED if mapped else HOLD_MAPPING_REQUIRED
    pms_status = "cancellation_pending" if is_cancellation else ("pending" if mapped else "pending_mapping")
    if current and (current.get("pms_booking_ids") or current.get("pms_booking_id")) and not is_cancellation and mapped:
        pms_status = "updated"

    now = datetime.now(UTC).isoformat()
    version_doc = {
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": "exely",
        "provider_reservation_id": external_id,
        "provider_reservation_id_context": canonical.get("provider_reservation_id_context", ""),
        "provider_version_key": version_key,
        "provider_created_at": created_at,
        "provider_payload_hash": payload_hash,
        "version_identity": identity,
        "event_type": "cancellation" if is_cancellation else event_type,
        "provider_state": canonical["status"],
        "room_stays": canonical["rooms"],
        "processing_state": processing_state,
        "mapping_state": mapping_code,
        "ack_state": ACK_NOT_READY,
        "raw_event_id": event_id,
        "updated_at": now,
    }
    await db.exely_reservation_versions.update_one(
        {"version_identity": identity},
        {"$set": version_doc, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
        upsert=True,
    )

    reservation_doc = _reservation_document(tenant_id, canonical, event_id, payload_hash, identity)
    reservation_doc["pms_status"] = pms_status
    if current and current.get("provider_version_identity"):
        current_query["provider_version_identity"] = current["provider_version_identity"]
    reservation_update = {
        "$set": reservation_doc,
        "$setOnInsert": {
            "id": str(uuid.uuid4()),
            "created_at": now,
            "pms_booking_id": None,
            "pms_booking_ids": [],
            "room_stay_lineage": [],
        },
        "$inc": {"provider_version_sequence": 1},
    }
    try:
        current_update = await db.exely_reservations.update_one(
            current_query,
            reservation_update,
            upsert=not bool(current),
        )
    except DuplicateKeyError:
        # Two first-delivery workers can both observe no current row before the
        # unique (tenant_id, external_id) index chooses one winner. Re-read the
        # winner and resolve the race without serializing Mongo's error text,
        # which may contain tenant and provider identifiers.
        winner = await db.exely_reservations.find_one(
            {"tenant_id": tenant_id, "external_id": external_id},
            {
                "_id": 0,
                "id": 1,
                "provider_version_key": 1,
                "provider_version_identity": 1,
                "provider_payload_hash": 1,
                "pms_booking_ids": 1,
                "pms_booking_id": 1,
            },
        )
        if not winner:
            raise

        winner_identity = str(winner.get("provider_version_identity") or "")
        winner_hash = str(winner.get("provider_payload_hash") or "")
        if winner_identity == identity:
            if winner_hash == payload_hash:
                return {"action": "skip", "reason": "duplicate_payload", "external_id": external_id}
            await mark_version_state(
                identity,
                processing_state=MALFORMED,
                ack_state=ACK_NOT_READY,
                failure_code="VERSION_PAYLOAD_CONFLICT",
            )
            return {"action": "error", "reason": "VERSION_PAYLOAD_CONFLICT", "external_id": external_id}

        winner_version = str(winner.get("provider_version_key") or "")
        if not winner_version:
            await mark_version_state(identity, ack_state=ACK_STALE, failure_code="CURRENT_VERSION_CHANGED")
            return {"action": "skip", "reason": "stale_event", "external_id": external_id}

        comparison = _compare_versions(version_key, winner_version)
        if comparison < 0:
            await mark_version_state(identity, ack_state=ACK_STALE)
            return {"action": "skip", "reason": "stale_event", "external_id": external_id}
        if comparison == 0:
            if winner_hash == payload_hash:
                return {"action": "skip", "reason": "duplicate_payload", "external_id": external_id}
            await mark_version_state(
                identity,
                processing_state=MALFORMED,
                ack_state=ACK_NOT_READY,
                failure_code="VERSION_PAYLOAD_CONFLICT",
            )
            return {"action": "error", "reason": "VERSION_PAYLOAD_CONFLICT", "external_id": external_id}

        if winner.get("pms_booking_ids") or winner.get("pms_booking_id"):
            reservation_doc["pms_status"] = "updated"
        retry_query = {"tenant_id": tenant_id, "external_id": external_id}
        if winner_identity:
            retry_query["provider_version_identity"] = winner_identity
        elif winner.get("id"):
            retry_query["id"] = winner["id"]
        else:
            await mark_version_state(identity, ack_state=ACK_STALE, failure_code="CURRENT_VERSION_CHANGED")
            return {"action": "skip", "reason": "stale_event", "external_id": external_id}
        current_update = await db.exely_reservations.update_one(
            retry_query,
            reservation_update,
            upsert=False,
        )
        current = winner
    if current and getattr(current_update, "modified_count", 0) != 1:
        await mark_version_state(identity, ack_state=ACK_STALE, failure_code="CURRENT_VERSION_CHANGED")
        return {"action": "skip", "reason": "stale_event", "external_id": external_id}

    if not mapped:
        from domains.channel_manager.providers.unmatched_hold import create_unmatched_reservation_hold

        first_room = (canonical.get("rooms") or [{}])[0]
        hold = await create_unmatched_reservation_hold(
            provider="exely",
            tenant_id=tenant_id,
            external_id=external_id,
            check_in=canonical["stay"]["check_in"],
            check_out=canonical["stay"]["check_out"],
            guest_name=canonical["guest"]["name"],
            room_type_code=str(first_room.get("room_type_code") or ""),
            rate_plan_code=str(first_room.get("rate_plan_code") or ""),
            total_amount=float(canonical["financial"]["total_amount"] or 0),
            currency=str(canonical["financial"]["currency"] or ""),
            adults=int(first_room.get("adults") or 1),
            children=int(first_room.get("children") or 0),
            channel=canonical["channel"],
            property_id=property_id,
        )
        if hold.get("booking_id"):
            await db.exely_reservations.update_one(
                {"provider_version_identity": identity},
                {"$set": {"hold_booking_id": hold["booking_id"]}},
            )
        if not hold.get("booking_id") or not hold.get("alarm_raised"):
            await mark_version_state(
                identity,
                failure_code="MAPPING_HOLD_NOT_DURABLE",
            )
            return {
                "action": "error",
                "reason": "MAPPING_HOLD_NOT_DURABLE",
                "external_id": external_id,
                "pms_status": pms_status,
            }
        return {
            "action": "hold",
            "reason": mapping_code,
            "external_id": external_id,
            "pms_status": pms_status,
        }

    action = "cancelled" if is_cancellation else ("updated" if current else "created")
    return {"action": action, "external_id": external_id, "pms_status": pms_status}


async def mark_version_state(version_identity_value: str, **fields: Any) -> None:
    fields["updated_at"] = datetime.now(UTC).isoformat()
    await db.exely_reservation_versions.update_one(
        {"version_identity": version_identity_value},
        {"$set": fields},
    )


async def _durable_readback(version_doc: dict[str, Any]) -> bool:
    expectations = version_doc.get("durable_expectations") or []
    if not expectations:
        return False
    for expected in expectations:
        booking = await db.bookings.find_one(
            {
                "tenant_id": version_doc["tenant_id"],
                "id": expected["pms_booking_id"],
            },
            {
                "_id": 0,
                "status": 1,
                "provider_version_key": 1,
                "inventory_release_pending": 1,
            },
        )
        if not booking or booking.get("status") != expected["status"]:
            return False
        if booking.get("provider_version_key") != version_doc["provider_version_key"]:
            return False
        if booking.get("inventory_release_pending"):
            return False
    return True


def _ack_confirmations_match_version(version_doc: dict[str, Any]) -> bool:
    confirmations = version_doc.get("ack_confirmations") or []
    if not confirmations:
        return False
    pms_ids = [str(row.get("pms_booking_id") or "") for row in confirmations]
    if any(not value for value in pms_ids) or len(set(pms_ids)) != len(pms_ids):
        return False
    if any(not str(row.get("pms_created_at") or "") for row in confirmations):
        return False
    confirmed_indexes = [str(index) for row in confirmations for index in row.get("room_stay_indexes") or [] if str(index)]
    if len(confirmations) > 1 and any(not (row.get("room_stay_indexes") or []) for row in confirmations):
        return False
    incoming_indexes = [str(room.get("index_number") or "") for room in version_doc.get("room_stays") or [] if str(room.get("index_number") or "")]
    return not incoming_indexes or sorted(confirmed_indexes) == sorted(incoming_indexes)


async def acknowledge_durable_version(provider, reservation: dict[str, Any]) -> dict[str, Any]:
    """Send at most one ACK for the current durable version; never auto-retry."""
    identity = str(reservation.get("provider_version_identity") or "")
    version_doc = await db.exely_reservation_versions.find_one(
        {"version_identity": identity},
        {"_id": 0},
    )
    if not version_doc or version_doc.get("processing_state") != PMS_DURABLE:
        return {"success": False, "provider_write_count": 0, "reason": "PMS_NOT_DURABLE"}
    if version_doc.get("ack_state") == ACKED:
        return {"success": True, "provider_write_count": 0, "reason": "ALREADY_ACKED"}
    if version_doc.get("ack_state") != ACK_PENDING:
        return {"success": False, "provider_write_count": 0, "reason": "ACK_NOT_PENDING"}
    if not _ack_confirmations_match_version(version_doc):
        await mark_version_state(
            identity,
            ack_state=ACK_NOT_READY,
            failure_code="ACK_CONFIRMATION_MAPPING_INVALID",
        )
        return {
            "success": False,
            "provider_write_count": 0,
            "reason": "ACK_CONFIRMATION_MAPPING_INVALID",
        }
    current = await db.exely_reservations.find_one(
        {
            "tenant_id": version_doc["tenant_id"],
            "property_id": version_doc["property_id"],
            "external_id": version_doc["provider_reservation_id"],
        },
        {"_id": 0, "provider_version_identity": 1, "delivery_state": 1},
    )
    if not current or current.get("provider_version_identity") != identity:
        await mark_version_state(identity, ack_state=ACK_STALE)
        return {"success": False, "provider_write_count": 0, "reason": "STALE_VERSION"}
    if current.get("delivery_state") != ACK_PENDING:
        return {"success": False, "provider_write_count": 0, "reason": "DELIVERY_NOT_PENDING"}
    if not await _durable_readback(version_doc):
        await mark_version_state(identity, processing_state=PMS_FAILED, ack_state=ACK_NOT_READY, failure_code="PMS_READBACK_FAILED")
        return {"success": False, "provider_write_count": 0, "reason": "PMS_READBACK_FAILED"}

    claim = await db.exely_reservation_versions.update_one(
        {"version_identity": identity, "ack_state": ACK_PENDING},
        {"$set": {"ack_state": ACK_SENDING, "ack_started_at": datetime.now(UTC).isoformat()}},
    )
    if getattr(claim, "modified_count", 0) != 1:
        return {"success": False, "provider_write_count": 0, "reason": "ACK_ALREADY_CLAIMED"}
    await db.exely_reservations.update_one(
        {"tenant_id": version_doc["tenant_id"], "provider_version_identity": identity},
        {"$set": {"delivery_state": ACK_SENDING}},
    )

    confirmations = version_doc.get("ack_confirmations") or []
    first_confirmation = confirmations[0]["pms_booking_id"] if confirmations else ""
    first_pms_created_at = confirmations[0]["pms_created_at"] if confirmations else ""
    try:
        result = await provider.confirm_delivery(
            version_doc["provider_reservation_id"],
            first_confirmation,
            create_datetime=first_pms_created_at,
            last_modify_datetime=version_doc["provider_version_key"],
            res_status="Reserved",
            provider_id_context=version_doc.get("provider_reservation_id_context", ""),
            confirmations=confirmations,
        )
    except Exception as exc:
        await mark_version_state(identity, ack_state=ACK_AMBIGUOUS, ack_error_type=type(exc).__name__)
        await db.exely_reservations.update_one(
            {"tenant_id": version_doc["tenant_id"], "provider_version_identity": identity},
            {"$set": {"delivery_state": ACK_AMBIGUOUS}},
        )
        logger.error("[EXELY-LIFECYCLE] ack_state=ambiguous exception_class=%s", type(exc).__name__)
        return {"success": False, "provider_write_count": 1, "reason": "ACK_AMBIGUOUS"}

    if not result.success:
        error_type = str(getattr(result, "error_type", "") or "ProviderRejected")
        ambiguous = error_type in {"ExelyTemporaryError", "ExelyParseError", "ExelyAckMalformed"}
        await mark_version_state(
            identity,
            ack_state=ACK_AMBIGUOUS if ambiguous else ACK_REJECTED,
            ack_error_type=error_type,
        )
        await db.exely_reservations.update_one(
            {"tenant_id": version_doc["tenant_id"], "provider_version_identity": identity},
            {"$set": {"delivery_state": ACK_AMBIGUOUS if ambiguous else ACK_REJECTED}},
        )
        return {
            "success": False,
            "provider_write_count": 1,
            "reason": "ACK_AMBIGUOUS" if ambiguous else "ACK_REJECTED",
        }

    acked_at = datetime.now(UTC).isoformat()
    await mark_version_state(identity, ack_state=ACKED, acked_at=acked_at)
    await db.exely_reservations.update_one(
        {"provider_version_identity": identity},
        {
            "$set": {
                "delivery_state": ACKED,
                "delivery_confirmed": True,
                "delivery_confirmed_version": version_doc["provider_version_key"],
                "delivery_confirmed_at": acked_at,
            }
        },
    )
    return {"success": True, "provider_write_count": 1, "reason": "ACKED"}


async def acknowledge_pending_versions(provider, tenant_id: str, limit: int = 50) -> dict[str, int]:
    reservations = await db.exely_reservations.find(
        {"tenant_id": tenant_id, "delivery_state": ACK_PENDING},
        {"_id": 0},
    ).to_list(limit)
    acked = 0
    writes = 0
    failed = 0
    for reservation in reservations:
        result = await acknowledge_durable_version(provider, reservation)
        writes += int(result.get("provider_write_count", 0))
        if result.get("success"):
            acked += 1
        else:
            failed += 1
    return {"acked": acked, "failed": failed, "provider_write_count": writes}
