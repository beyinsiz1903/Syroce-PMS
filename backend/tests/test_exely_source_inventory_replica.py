"""Real unique-index/crash tests; explicit LOCAL MongoDB only, no provider."""
import asyncio
import os
import uuid
from copy import deepcopy
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from core.outbox_service import ensure_outbox_indexes
from domains.channel_manager.providers.exely import reservation_inventory as inventory


@pytest_asyncio.fixture
async def database():
    uri = os.getenv("EXELY_INVENTORY_TEST_MONGO_URI") or os.getenv("POS_TEST_MONGO_URI")
    assert uri and urlparse(uri).hostname in {"localhost", "127.0.0.1"}, "Explicit LOCAL MongoDB required"
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    db = client["exely_inventory_test_" + uuid.uuid4().hex]
    await ensure_outbox_indexes(db)
    yield db
    await client.drop_database(db.name)
    client.close()


async def version(db):
    row = {"version_identity": "synthetic-version", "tenant_id": "synthetic-tenant",
        "property_id": "synthetic-property", "ack_state": "ACKED", "inventory_outbox_state": "PENDING",
        "inventory_targets_v1": [{"room_type": "Standard", "date_from": "2030-01-01", "date_to": "2030-01-03"}]}
    await db.exely_reservation_versions.insert_one(deepcopy(row))
    await db.exely_reservations.insert_one({"tenant_id": row["tenant_id"],
        "provider_version_identity": row["version_identity"], "inventory_outbox_state": "PENDING"})
    return row


@pytest.mark.asyncio
async def test_concurrent_acked_enqueue_has_one_real_persisted_event(database):
    row = await version(database)
    await asyncio.gather(*(inventory.enqueue_after_ack(database, deepcopy(row)) for _ in range(25)))
    assert await database.outbox_events.count_documents({}) == 1
    event = await database.outbox_events.find_one({})
    assert event["provider"] == "exely" and event["status"] == "pending" and event["attempt_count"] == 0
    assert event["idempotency_key"] == "exely-inventory-v1:synthetic-version"
    assert (await database.exely_reservation_versions.find_one({}))["inventory_outbox_state"] == "QUEUED"


@pytest.mark.asyncio
async def test_lost_local_insert_result_is_deduplicated_by_real_unique_index(database, monkeypatch):
    row = await version(database)
    real_enqueue = inventory.enqueue_outbox_event

    async def lost_response(*args, **kwargs):
        await real_enqueue(*args, **kwargs)
        raise TimeoutError("synthetic lost local insert response")

    monkeypatch.setattr(inventory, "enqueue_outbox_event", lost_response)
    with pytest.raises(TimeoutError):
        await inventory.enqueue_after_ack(database, row)
    assert await database.outbox_events.count_documents({}) == 1
    assert (await database.exely_reservation_versions.find_one({}))["inventory_outbox_state"] == "PENDING"
    monkeypatch.setattr(inventory, "enqueue_outbox_event", real_enqueue)
    await inventory.enqueue_after_ack(database, row)
    assert await database.outbox_events.count_documents({}) == 1
    assert (await database.exely_reservations.find_one({}))["inventory_outbox_state"] == "QUEUED"


@pytest.mark.asyncio
async def test_original_before_snapshot_survives_new_claim_generation(database):
    tenant, identity = "synthetic-tenant", "synthetic-version"
    await database.exely_reservation_versions.insert_one({"tenant_id": tenant, "version_identity": identity,
        "processing_owner_token": "first"})
    await database.exely_connections.insert_one({"tenant_id": tenant, "is_active": True,
        "hotel_code": "synthetic-property", "ari_write_enabled": True})
    await database.bookings.insert_one({"tenant_id": tenant, "id": "synthetic-booking", "status": "confirmed",
        "room_type": "Standard", "room_id": None, "check_in": "2030-01-01", "check_out": "2030-01-03"})
    first = await inventory.capture_before(database, tenant, identity, "synthetic-property", ["synthetic-booking"],
        {"version_identity": identity, "processing_owner_token": "first"})
    await database.bookings.update_one({"id": "synthetic-booking"}, {"$set": {"check_out": "2030-01-04"}})
    await database.exely_reservation_versions.update_one({"version_identity": identity},
        {"$set": {"processing_owner_token": "second"}})
    second = await inventory.capture_before(database, tenant, identity, "synthetic-property", ["synthetic-booking"],
        {"version_identity": identity, "processing_owner_token": "second"})
    assert first == second
    assert await inventory.finish_plan(database, tenant, second) == [
        {"room_type": "Standard", "date_from": "2030-01-03", "date_to": "2030-01-04"}]
