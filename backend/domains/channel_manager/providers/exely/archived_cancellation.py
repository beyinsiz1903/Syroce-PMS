"""Durable cancellation receipts for three reviewed TEST501694 sources.

This does not cancel anything at Exely or authorize acceptance of provider terms.
Only an actual incoming cancellation can be recorded. The original PMS booking,
archive receipt, guest and financial sources remain byte-for-byte unchanged.
Unknown archives and all non-cancellation updates remain fail-closed.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException

from core.audit_chain import compute_record_hash
from core.booking_atomicity import with_resource_locks
from modules.pms_core.demo_presentation_archive import FINANCIAL, POLICY, TENANT, digest, guard
from shared_kernel.audit_helper import audit_log

REVIEWED = {
    "05cc2a5f-b4ac-5e25-81a2-7aa3e2c72382": "20261110-501694-1200421158",
    "4a4bf51e-82c7-5972-aefe-90b4525e0012": "20261110-501694-1200421078",
    "bd6dd709-d7e7-50f7-bd13-0e3de7756525": "20261110-501694-1200418715",
    "81ee0d74-bccb-5112-b275-61767f6e1eec": "20261110-501694-1200418715",
}
BLOCKED = "PMS_ARCHIVED_SOURCE_REQUIRES_REVIEW"
COLLECTION = "exely_archived_cancellations"
ACTION = "exely_archived_demo_cancellation_recorded"


def is_archived(booking):
    return bool(booking and (booking.get("status") == "archived_demo"
        or booking.get("presentation_archive") or booking.get("allocation_source") == "archived_demo_cleanup"))


def _sealed(entry):
    return bool(entry and isinstance(entry.get("seq"), int) and entry.get("record_hash")
        == compute_record_hash(entry, entry["seq"], entry.get("prev_hash", "")))


async def _guard_reviewed(database, tenant_id, session=None):
    day = await guard(database, tenant_id, session)
    connections = await database.exely_connections.find({"tenant_id": tenant_id, "is_active": True},
        {"_id": 0, "hotel_code": 1}, session=session).to_list(None)
    if day != "2026-10-26" or len(connections) != 1 or str(connections[0].get("hotel_code")) != "501694":
        raise HTTPException(409, "İncelenmiş Demo TEST bağlantısı ve açık iş günü doğrulanamadı")
    return day


async def _archive_proof(database, tenant_id, booking, session=None):
    bid = booking["id"]
    marker = booking.get("presentation_archive") or {}
    if tenant_id != TENANT or bid not in REVIEWED or not isinstance(marker, dict) or marker.get("policy_id") != POLICY:
        raise RuntimeError(BLOCKED)
    receipt = await database.demo_presentation_archives.find_one(
        {"tenant_id": tenant_id, "policy_id": POLICY, "request_id": marker.get("request_id")},
        {"_id": 0}, session=session)
    rows = [row for row in (receipt or {}).get("before_images", []) if row.get("booking", {}).get("id") == bid]
    if not receipt or len(rows) != 1 or bid not in receipt.get("result", {}).get("archived_ids", []):
        raise RuntimeError(BLOCKED)
    expected = {**rows[0]["booking"], "status": "archived_demo", "allocation_source": "archived_demo_cleanup",
        "updated_at": receipt["created_at"], "updated_by": receipt["actor_id"], "presentation_archive": {
            "policy_id": POLICY, "request_id": receipt["request_id"], "reason": receipt["reason"],
            "archived_at": receipt["created_at"], "archived_by": receipt["actor_id"]}}
    if digest(booking) != digest(expected):
        raise RuntimeError(BLOCKED)
    before_hash = digest(rows[0])
    audit = await database.audit_logs.find_one({"tenant_id": tenant_id, "entity_id": bid,
        "action": "demo_reservation_archived", "metadata.request_id": receipt["request_id"],
        "metadata.before_hash": before_hash}, {"_id": 0}, session=session)
    if not _sealed(audit):
        raise RuntimeError(BLOCKED)
    return {"archive_request_id": receipt["request_id"], "archive_before_hash": before_hash,
        "source_hash": digest(booking)}


async def _no_live_sources(database, tenant_id, bid, session=None):
    folios = await database.folios.find({"tenant_id": tenant_id, "booking_id": bid}, {"_id": 0}, session=session).to_list(None)
    if any(row.get("status") != "closed" or float(row.get("balance") or 0) for row in folios):
        raise RuntimeError(BLOCKED)
    scope = {"tenant_id": tenant_id, "$or": [{"booking_id": bid}, {"reservation_id": bid},
        {"folio_id": {"$in": [row["id"] for row in folios]}}]}
    for collection in (*FINANCIAL, "spa_appointments", "minibar_consumptions", "pos_orders", "room_night_locks"):
        if await database[collection].count_documents(scope, session=session):
            raise RuntimeError(BLOCKED)


async def record_cancellation(database, tenant_id, booking_id, version_key, claim_query):
    if tenant_id != TENANT or booking_id not in REVIEWED:
        raise RuntimeError(BLOCKED)
    # Create indexes outside the transaction; there is no standalone fallback.
    await database[COLLECTION].create_index([("tenant_id", 1), ("id", 1)], unique=True)
    await database.minibar_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True)
    identity = claim_query["version_identity"]
    receipt_id = digest([tenant_id, booking_id, version_key])

    async def commit(session):
        await _guard_reviewed(database, tenant_id, session)
        now = datetime.now(UTC).isoformat()
        # Writing the claimed version in the same transaction fences takeover
        # before commit. No lost worker can commit an orphan success receipt.
        claimed = await database.exely_reservation_versions.update_one(
            {**claim_query, "tenant_id": tenant_id, "provider_version_key": version_key, "event_type": "cancellation"},
            {"$set": {"processing_heartbeat_at": now}}, session=session)
        if claimed.matched_count != 1:
            raise RuntimeError(BLOCKED)
        current = await database.exely_reservations.find_one({"tenant_id": tenant_id, "property_id": "501694",
            "external_id": REVIEWED[booking_id], "provider_version_identity": identity, "state": "cancelled"},
            {"_id": 0}, session=session)
        if not current or not any(row.get("pms_booking_id") == booking_id and row.get("active", True)
                                 for row in current.get("room_stay_lineage", [])):
            raise RuntimeError(BLOCKED)
        booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": booking_id}, {"_id": 0}, session=session)
        if not booking:
            raise RuntimeError(BLOCKED)
        proof = await _archive_proof(database, tenant_id, booking, session)
        await _no_live_sources(database, tenant_id, booking_id, session)
        receipt = await database[COLLECTION].find_one({"tenant_id": tenant_id, "id": receipt_id}, {"_id": 0}, session=session)
        if receipt:
            if any(receipt.get(key) != value for key, value in proof.items()) or receipt.get("version_identity") != identity:
                raise RuntimeError(BLOCKED)
        else:
            receipt = {"tenant_id": tenant_id, "id": receipt_id, "booking_id": booking_id, "policy_id": POLICY,
                "property_id": "501694", "external_id": REVIEWED[booking_id], "version_identity": identity,
                "provider_version_key": version_key, "provider_state": "cancelled", "recorded_at": now,
                "actor_id": "channel_manager", "reason": "reviewed_test_source_provider_cancellation",
                "booking_changed": False, "financial_sources_changed": False, **proof}
            audit = await audit_log(actor_id="channel_manager", tenant_id=tenant_id, entity_type="reservation",
                entity_id=booking_id, action=ACTION, metadata=receipt, session=session, require_chain=True)
            receipt = {**receipt, "audit_id": audit["id"], "audit_hash": audit["record_hash"]}
            await database[COLLECTION].insert_one(dict(receipt), session=session)
        return {"pms_booking_id": booking_id, "status": "archived_demo",
            "archived_cancellation_id": receipt_id, "archived_cancellation_hash": digest(receipt)}

    return await with_resource_locks(client=database.client, db=database, tenant_id=tenant_id,
        locks_collection="minibar_locks", resources=[("demo_archive", tenant_id), ("booking", booking_id)], callback=commit)


async def readback(database, tenant_id, version_key, expected):
    if tenant_id != TENANT or expected.get("pms_booking_id") not in REVIEWED:
        return False
    receipt = await database[COLLECTION].find_one({"tenant_id": tenant_id,
        "id": expected.get("archived_cancellation_id")}, {"_id": 0})
    bid = expected["pms_booking_id"]
    if not receipt or digest(receipt) != expected.get("archived_cancellation_hash") or any((
        receipt.get("booking_id") != bid, receipt.get("external_id") != REVIEWED[bid],
        receipt.get("provider_version_key") != version_key, receipt.get("provider_state") != "cancelled")):
        return False
    version = await database.exely_reservation_versions.find_one({"tenant_id": tenant_id,
        "version_identity": receipt.get("version_identity"), "provider_version_key": version_key,
        "property_id": "501694", "provider_reservation_id": REVIEWED[bid], "event_type": "cancellation"}, {"_id": 0, "id": 1})
    if not version:
        return False
    booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": bid}, {"_id": 0})
    if not booking or digest(booking) != receipt.get("source_hash"):
        return False
    try:
        proof = await _archive_proof(database, tenant_id, booking)
        await _no_live_sources(database, tenant_id, bid)
    except (RuntimeError, KeyError, TypeError, ValueError):
        return False
    if any(receipt.get(key) != value for key, value in proof.items()):
        return False
    audit = await database.audit_logs.find_one({"tenant_id": tenant_id, "id": receipt.get("audit_id"),
        "entity_id": bid, "action": ACTION}, {"_id": 0})
    return bool(_sealed(audit) and audit["record_hash"] == receipt.get("audit_hash")
        and audit.get("metadata") == {key: value for key, value in receipt.items() if key not in {"audit_id", "audit_hash"}})


async def preview(database, tenant_id):
    """GET-only readiness; never proof of provider terms/fees or cancellation."""
    day = await _guard_reviewed(database, tenant_id)
    sources = []
    for external in sorted(set(REVIEWED.values())):
        ids = sorted(bid for bid, source in REVIEWED.items() if source == external)
        row = {"external_id": external, "pms_booking_ids": ids, "ready_for_provider_review": False,
            "cancellation_recorded": False, "reason": BLOCKED}
        try:
            if day != "2026-10-26":
                raise RuntimeError(BLOCKED)
            current = await database.exely_reservations.find_one({"tenant_id": tenant_id,
                "property_id": "501694", "external_id": external}, {"_id": 0})
            if not current or sorted(item.get("pms_booking_id", "") for item in current.get("room_stay_lineage", [])) != ids:
                raise RuntimeError(BLOCKED)
            proofs = {}
            for bid in ids:
                booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": bid}, {"_id": 0})
                if not booking:
                    raise RuntimeError(BLOCKED)
                proofs[bid] = await _archive_proof(database, tenant_id, booking)
                await _no_live_sources(database, tenant_id, bid)
            if current.get("state") == "confirmed" and all(item.get("active", True) for item in current["room_stay_lineage"]):
                row.update(ready_for_provider_review=True, reason="REVIEWED_ARCHIVE_INTACT", archive_proofs=proofs)
            elif current.get("state") == "cancelled" and current.get("pms_status") == "cancellation_done":
                version = await database.exely_reservation_versions.find_one({"tenant_id": tenant_id,
                    "version_identity": current.get("provider_version_identity")}, {"_id": 0})
                expectations = (version or {}).get("durable_expectations", [])
                if sorted(item.get("pms_booking_id", "") for item in expectations) != ids:
                    raise RuntimeError(BLOCKED)
                for expected in expectations:
                    if not await readback(database, tenant_id, version["provider_version_key"], expected):
                        raise RuntimeError(BLOCKED)
                row.update(cancellation_recorded=True, reason="CANCELLATION_RECEIPT_VERIFIED", archive_proofs=proofs)
        except (RuntimeError, KeyError, TypeError, ValueError):
            pass
        sources.append(row)
    return {"policy_id": POLICY, "business_date": day, "sources": sources,
        "provider_write_count": 0, "provider_terms_accepted": False, "fee_verified": False}
