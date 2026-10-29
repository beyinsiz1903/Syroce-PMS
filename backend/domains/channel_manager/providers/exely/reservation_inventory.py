"""Durable, ACK-ordered inventory deltas for NEW Exely source versions.

No historical backfill: a before-image is armed only while this exact active
connection has tenant ARI enabled. No quantity is stored/replayed. Consumers
recalculate current canonical inventory under the unchanged commercial cap.
"""
from collections import Counter, defaultdict
from datetime import date

from core.outbox_service import EXELY_RESERVATION_INVENTORY, enqueue_outbox_event
from domains.channel_manager.providers.exely import archived_cancellation

ACTIVE = {"pending", "confirmed", "guaranteed", "checked_in", "in_house", "reserved"}


async def footprints(database, tenant_id, booking_ids):
    ids = sorted(set(booking_ids))
    rows = await database.bookings.find({"tenant_id": tenant_id, "id": {"$in": ids}},
        {"_id": 0, "id": 1, "status": 1, "room_id": 1, "room_type": 1,
         "check_in": 1, "check_out": 1, "presentation_archive": 1, "allocation_source": 1}).to_list(len(ids) + 1)
    if len(rows) > len(ids) or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("EXELY_INVENTORY_SOURCE_AMBIGUOUS")
    result = []
    for row in rows:
        if row.get("status") not in ACTIVE or archived_cancellation.is_archived(row):
            continue
        kind = row.get("room_type")
        if row.get("room_id"):
            room = await database.rooms.find_one({"tenant_id": tenant_id, "id": row["room_id"]},
                                                 {"_id": 0, "room_type": 1})
            if room:
                kind = room.get("room_type")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("EXELY_INVENTORY_CATEGORY_MISSING")
        start = date.fromisoformat(str(row.get("check_in") or "")[:10])
        end = date.fromisoformat(str(row.get("check_out") or "")[:10])
        if end <= start:
            raise ValueError("EXELY_INVENTORY_DATES_INVALID")
        result.append({"room_type": kind, "date_from": start.isoformat(), "date_to": end.isoformat()})
    return result


def changed_ranges(before, after):
    """Compare room-night MULTISETS without iterating every calendar day."""
    boundaries = defaultdict(Counter)
    for sign, rows in ((1, before), (-1, after)):
        for row in rows:
            boundaries[row["room_type"]][row["date_from"]] += sign
            boundaries[row["room_type"]][row["date_to"]] -= sign
    result = []
    for kind, changes in sorted(boundaries.items()):
        count, previous = 0, None
        for day, delta in sorted(changes.items()):
            if previous is not None and count:
                if result and result[-1]["room_type"] == kind and result[-1]["date_to"] == previous:
                    result[-1]["date_to"] = day
                else:
                    result.append({"room_type": kind, "date_from": previous, "date_to": day})
            count += delta
            previous = day
    return result


async def capture_before(database, tenant_id, identity, property_id, booking_ids, owned_query):
    query = {**owned_query, "tenant_id": tenant_id, "version_identity": identity}
    version = await database.exely_reservation_versions.find_one(query, {"_id": 0})
    if not version:
        raise RuntimeError("PROCESSING_CLAIM_LOST")
    if "inventory_before_v1" in version:
        return version["inventory_before_v1"]
    connection = await database.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "hotel_code": 1, "ari_write_enabled": 1})
    armed = bool(property_id and connection and connection.get("ari_write_enabled") is True
                 and str(connection.get("hotel_code") or "") == property_id)
    snapshot = {"armed": armed, "booking_ids": sorted(set(booking_ids)),
                "footprints": await footprints(database, tenant_id, booking_ids) if armed else []}
    saved = await database.exely_reservation_versions.update_one(
        {**query, "inventory_before_v1": {"$exists": False}}, {"$set": {"inventory_before_v1": snapshot}})
    if saved.matched_count != 1:
        raise RuntimeError("PROCESSING_CLAIM_LOST")
    return snapshot


async def finish_plan(database, tenant_id, before):
    if not before["armed"]:
        return []
    after = await footprints(database, tenant_id, before["booking_ids"])
    return changed_ranges(before["footprints"], after)


async def enqueue_after_ack(database, version):
    """Idempotent local enqueue; never send/repeat ACK or contact a provider."""
    targets = version.get("inventory_targets_v1")
    if version.get("ack_state") != "ACKED" or not targets:
        return
    identity, tenant_id = version["version_identity"], version["tenant_id"]
    if version.get("inventory_outbox_state") != "QUEUED":
        await enqueue_outbox_event(database, tenant_id=tenant_id,
            event_type=EXELY_RESERVATION_INVENTORY, provider="exely",
            entity_type="exely_reservation_version", entity_id=identity,
            property_id=version["property_id"],
            idempotency_key=f"exely-inventory-v1:{identity}",
            payload={"version_identity": identity, "targets": targets})
        await database.exely_reservation_versions.update_one(
            {"version_identity": identity, "tenant_id": tenant_id, "ack_state": "ACKED"},
            {"$set": {"inventory_outbox_state": "QUEUED"}})
    await database.exely_reservations.update_one(
        {"tenant_id": tenant_id, "provider_version_identity": identity},
        {"$set": {"inventory_outbox_state": "QUEUED"}})


async def checked_event(database, event):
    """Validate persisted source authority before any inventory/provider work."""
    payload = event.get("payload") or {}
    tenant_id = event.get("tenant_id")
    identity = payload.get("version_identity") if isinstance(payload, dict) else None
    if (event.get("event_type") != EXELY_RESERVATION_INVENTORY or event.get("provider") != "exely"
            or not tenant_id or not identity or event.get("entity_id") != identity):
        raise ValueError("exely_inventory_source_invalid")
    version = await database.exely_reservation_versions.find_one(
        {"tenant_id": tenant_id, "version_identity": identity}, {"_id": 0})
    if (not version or version.get("ack_state") != "ACKED" or version.get("processing_state") != "PMS_DURABLE"
            or not (version.get("inventory_before_v1") or {}).get("armed")
            or event.get("property_id") != version.get("property_id")
            or payload.get("targets") != version.get("inventory_targets_v1") or not payload.get("targets")):
        raise ValueError("exely_inventory_source_invalid")
    ids = version["inventory_before_v1"]["booking_ids"]
    for bid in ids:
        booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": bid},
            {"_id": 0, "id": 1, "status": 1, "presentation_archive": 1, "allocation_source": 1})
        if not booking:
            raise ValueError("exely_inventory_source_invalid")
        if archived_cancellation.is_archived(booking):
            raise ValueError("exely_inventory_source_archived")
    connection = await database.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "hotel_code": 1, "ari_write_enabled": 1})
    if not connection or str(connection.get("hotel_code") or "") != str(version["property_id"]):
        raise ValueError("exely_property_mapping_missing")
    if connection.get("ari_write_enabled") is not True:
        raise ValueError("exely_ari_write_disabled")
    targets = payload["targets"]
    for target in targets:
        if set(target) != {"room_type", "date_from", "date_to"} or not target["room_type"]:
            raise ValueError("exely_inventory_source_invalid")
        start, end = date.fromisoformat(target["date_from"]), date.fromisoformat(target["date_to"])
        if not 0 < (end - start).days <= 366:
            # An outbound resource bound, NOT a claim about Exely's maximum.
            raise ValueError("exely_inventory_range_requires_review")
    return targets


async def check_mappings(database, tenant_id, targets):
    from domains.channel_manager.availability_auto_sync import _exely_wire_pair

    for kind in sorted({row["room_type"] for row in targets}):
        mappings = await database.exely_room_mappings.find(
            {"tenant_id": tenant_id, "pms_room_type": kind, "sync_availability": {"$ne": False}},
            {"_id": 0}).to_list(11)
        if not mappings:
            raise ValueError("exely_room_mapping_missing")
        if len(mappings) > 10 or any(not all(_exely_wire_pair(row)) for row in mappings):
            raise ValueError("exely_room_mapping_incomplete")
        if len({_exely_wire_pair(row) for row in mappings}) != 1:
            raise ValueError("exely_multiple_availability_mappings")


async def dispatch(event):
    """Exely-only current recompute; no generic connectors/agency fan-out."""
    from core.database import db
    from domains.channel_manager.availability_auto_sync import _load_authoritative_availability, _push_to_exely
    from domains.channel_manager.providers.exely.production_safety import ari_write_block_reason

    try:
        runtime_block = ari_write_block_reason()
        if runtime_block:
            return False, "permanent: " + runtime_block
        targets = await checked_event(db, event)
        await check_mappings(db, event["tenant_id"], targets)
        # Validate/read ALL categories first; a later failure must not leave a
        # half-planned date/category batch in the ARI queue.
        plans = []
        for target in targets:
            availability = await _load_authoritative_availability(event["tenant_id"], target["room_type"],
                date.fromisoformat(target["date_from"]), date.fromisoformat(target["date_to"]))
            plans.append((target["room_type"], availability))
        queued = 0
        for kind, availability in plans:
            result = await _push_to_exely(event["tenant_id"], kind, availability)
            if result.get("errors") or not result.get("queued_operations"):
                return False, "retryable: exely_inventory_enqueue_failed"
            queued += result["queued_operations"]
        return True, f"Dispatched: {queued} Exely category inventory operations queued"
    except ValueError as exc:
        # Codes are local allowlisted validation errors, never raw provider XML.
        code = str(exc)
        return False, "permanent: " + (code if code.startswith("exely_") else "exely_inventory_source_invalid")
    except Exception:
        return False, "retryable: exely_inventory_enqueue_failed"
