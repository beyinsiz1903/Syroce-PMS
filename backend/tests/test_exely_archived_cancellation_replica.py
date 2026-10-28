"""Reviewed archive cancellation: explicitly local replica set, no vendor calls."""
# ruff: noqa: F811
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from core.security import get_current_user
from domains.channel_manager.providers.exely import archived_cancellation as subject
from domains.channel_manager.providers.exely import lifecycle, pms_lifecycle
from modules.pms_core import demo_presentation_archive as archive
from routers import reservation_detail as api
from tests.test_demo_presentation_archive_replica import actor, request, seeded  # noqa: F401
from tests.test_exely_reservation_lifecycle import _canonical, _room
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest_asyncio.fixture
async def scenario(seeded, monkeypatch):
    monkeypatch.setattr(lifecycle, "db", seeded)
    monkeypatch.setattr(pms_lifecycle, "db", seeded)
    release = AsyncMock(return_value=0)
    monkeypatch.setattr("core.atomic_booking.release_booking_nights", release)
    for bid, external in subject.REVIEWED.items():
        await seeded.bookings.update_one({"id": bid}, {"$set": {
            "created_at": "2026-10-20T10:00:00+00:00", "provider_version_key": "2026-10-20T10:00:00+00:00",
            "provider_group_reservation_id": external, "currency": "USD",
            "daily_rates": [{"date": "2026-11-10", "amount": 100}], "tax_rate": .1}})
    await archive.apply(seeded, actor(), await request(seeded))
    for name in (subject.COLLECTION, "exely_reservations", "exely_reservation_versions"):
        await seeded.create_collection(name)
    return SimpleNamespace(db=seeded, release=release)


async def incoming(database, external="20261110-501694-1200418715", status="cancelled", version="2026-10-28T12:00:00Z"):
    ids = [bid for bid, source in subject.REVIEWED.items() if source == external]
    rooms = [_room(str(i + 1)) for i in range(len(ids))]
    canonical = _canonical(version, rooms, status)
    canonical.update(external_id=external, provider_reservation_id=external, property_id="501694")
    await database.exely_reservations.insert_one({"tenant_id": archive.TENANT, "property_id": "501694",
        "id": "source-" + external, "external_id": external,
        "room_stay_lineage": [{"slot_ordinal": i, "index_number": str(i + 1), "pms_booking_id": bid, "active": True}
                              for i, bid in enumerate(ids)]})
    if status != "cancelled":
        await database.exely_room_mappings.insert_one({"tenant_id": archive.TENANT,
            "id": "mapping", "exely_room_code": "STD", "exely_rate_plan_code": "BAR", "pms_room_type": "Standard"})
    assert (await lifecycle.persist_exely_event(archive.TENANT, canonical,
        "cancellation" if status == "cancelled" else "modification", "event", "hash"))["action"] in {"updated", "created", "cancelled"}
    return await database.exely_reservations.find_one({"external_id": external}, {"_id": 0})


async def snapshot(database):
    return {name: await database[name].find({}, {"_id": 0}).sort("id", 1).to_list(None)
            for name in ("bookings", "guests", "demo_presentation_archives", "folios", "room_night_locks", "rooms")}


@pytest.mark.parametrize("external", sorted(set(subject.REVIEWED.values())))
async def test_exact_reviewed_source_cancellation_preserves_all_archives_and_acks_once(scenario, external):
    database = scenario.db
    current = await incoming(database, external)
    before = await snapshot(database)
    result = await pms_lifecycle.process_reservation_version(archive.TENANT, current)
    assert result["success"] is True
    ids = [bid for bid, source in subject.REVIEWED.items() if source == external]
    assert result["cancelled"] == len(ids) and set(result["pms_booking_ids"]) == set(ids)
    assert await snapshot(database) == before
    assert await database[subject.COLLECTION].count_documents({}) == len(ids)
    assert await database.audit_logs.count_documents({"action": subject.ACTION}) == len(ids)
    scenario.release.assert_not_awaited()
    fresh = await database.exely_reservations.find_one({"external_id": external}, {"_id": 0})
    provider = SimpleNamespace(confirm_delivery=AsyncMock(return_value=SimpleNamespace(success=True)))
    assert (await lifecycle.acknowledge_durable_version(provider, fresh))["success"]
    assert {row["pms_booking_id"] for row in provider.confirm_delivery.await_args.kwargs["confirmations"]} == set(ids)
    assert (await lifecycle.acknowledge_durable_version(provider, fresh))["provider_write_count"] == 0
    assert (await pms_lifecycle.process_reservation_version(archive.TENANT, fresh))["success"]
    provider.confirm_delivery.assert_awaited_once()
    assert await snapshot(database) == before


@pytest.mark.parametrize("change", ["financial", "service", "lock", "folio", "archive", "before_image", "archive_audit",
    "booking", "tenant", "property", "business_date", "ari", "pull", "lineage", "claim", "missing_connection", "duplicate_connection"])
async def test_unreviewed_or_changed_source_blocks_receipt_and_ack(scenario, change, monkeypatch):
    database = scenario.db
    current = await incoming(database)
    bid = next(bid for bid, source in subject.REVIEWED.items() if source == current["external_id"])
    if change in {"financial", "service", "lock"}:
        collection = {"financial": "payments", "service": "spa_appointments", "lock": "room_night_locks"}[change]
        await database[collection].insert_one({"tenant_id": archive.TENANT, "booking_id": bid})
    elif change == "folio":
        await database.folios.insert_one({"id": "reopened", "tenant_id": archive.TENANT, "booking_id": bid, "status": "open", "balance": 0})
    elif change == "archive":
        await database.demo_presentation_archives.delete_many({})
    elif change == "before_image":
        await database.demo_presentation_archives.update_one({}, {"$set": {"reason": "changed"}})
    elif change == "archive_audit":
        await database.audit_logs.update_one({"entity_id": bid}, {"$set": {"record_hash": "broken"}})
    elif change == "booking":
        await database.bookings.update_one({"id": bid}, {"$set": {"total_amount": 101}})
    elif change == "tenant":
        await database.tenants.update_one({"id": archive.TENANT}, {"$set": {"hotel_id": "another"}})
    elif change in {"property", "lineage"}:
        await database.exely_reservations.update_one({"external_id": current["external_id"]},
            {"$set": {"property_id": "other"} if change == "property" else {"room_stay_lineage.0.pms_booking_id": "unknown"}})
    elif change == "business_date":
        await database.tenant_settings.update_one({"tenant_id": archive.TENANT}, {"$set": {"business_date": "2026-10-27"}})
    elif change in {"ari", "pull"}:
        await database.exely_connections.update_one({}, {"$set": {"ari_write_enabled" if change == "ari" else "auto_sync_reservations": True}})
    elif change == "missing_connection":
        await database.exely_connections.delete_many({})
    elif change == "duplicate_connection":
        duplicate = await database.exely_connections.find_one({}, {"_id": 0})
        await database.exely_connections.insert_one(duplicate)
    elif change == "claim":
        original = subject.record_cancellation
        async def lost(database, tenant_id, booking_id, version_key, claim_query):
            await database.exely_reservation_versions.update_one({"version_identity": current["provider_version_identity"]},
                {"$inc": {"processing_generation": 1}})
            return await original(database, tenant_id, booking_id, version_key, claim_query)
        monkeypatch.setattr(subject, "record_cancellation", lost)
    before = await snapshot(database)
    result = await pms_lifecycle.process_reservation_version(archive.TENANT, current)
    assert not result["success"]
    assert await snapshot(database) == before
    assert await database[subject.COLLECTION].count_documents({}) == 0
    provider = SimpleNamespace(confirm_delivery=AsyncMock())
    assert (await lifecycle.acknowledge_durable_version(provider, current))["provider_write_count"] == 0
    provider.confirm_delivery.assert_not_awaited()
    scenario.release.assert_not_awaited()


@pytest.mark.parametrize("change", ["booking", "receipt", "audit", "archive", "lock", "expectation"])
async def test_durable_readback_tamper_never_enables_ack(scenario, change):
    database = scenario.db
    current = await incoming(database)
    assert (await pms_lifecycle.process_reservation_version(archive.TENANT, current))["success"]
    version = await database.exely_reservation_versions.find_one({"version_identity": current["provider_version_identity"]}, {"_id": 0})
    expected = version["durable_expectations"][0]
    if change == "booking":
        await database.bookings.update_one({"id": expected["pms_booking_id"]}, {"$set": {"currency": "EUR"}})
    elif change == "receipt":
        await database[subject.COLLECTION].update_one({"id": expected["archived_cancellation_id"]}, {"$set": {"provider_state": "confirmed"}})
    elif change == "audit":
        await database.audit_logs.update_one({"action": subject.ACTION}, {"$set": {"record_hash": "broken"}})
    elif change == "archive":
        await database.demo_presentation_archives.delete_many({})
    elif change == "lock":
        await database.room_night_locks.insert_one({"tenant_id": archive.TENANT, "booking_id": expected["pms_booking_id"]})
    else:
        version["durable_expectations"][0].pop("archived_cancellation_hash")
        await database.exely_reservation_versions.update_one({"version_identity": current["provider_version_identity"]},
            {"$set": {"durable_expectations": version["durable_expectations"]}})
    assert not await pms_lifecycle._readback_expectations(archive.TENANT, version["provider_version_key"], version["durable_expectations"])
    assert not await lifecycle._durable_readback(version)
    provider = SimpleNamespace(confirm_delivery=AsyncMock())
    fresh = await database.exely_reservations.find_one({"external_id": current["external_id"]}, {"_id": 0})
    assert (await lifecycle.acknowledge_durable_version(provider, fresh))["provider_write_count"] == 0
    provider.confirm_delivery.assert_not_awaited()


async def test_audit_failure_rolls_back_cancellation_receipt(scenario, monkeypatch):
    database = scenario.db
    current = await incoming(database)
    before = await snapshot(database)
    monkeypatch.setattr(subject, "audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    assert not (await pms_lifecycle.process_reservation_version(archive.TENANT, current))["success"]
    assert await database[subject.COLLECTION].count_documents({}) == 0
    assert await database.audit_logs.count_documents({"action": subject.ACTION}) == 0
    assert await snapshot(database) == before


async def test_crash_after_receipt_replays_once_with_one_audit_per_room(scenario, monkeypatch):
    database = scenario.db
    current = await incoming(database)
    real = pms_lifecycle._readback_expectations
    monkeypatch.setattr(pms_lifecycle, "_readback_expectations", AsyncMock(side_effect=RuntimeError("readback interrupted")))
    assert not (await pms_lifecycle.process_reservation_version(archive.TENANT, current))["success"]
    monkeypatch.setattr(pms_lifecycle, "_readback_expectations", real)
    assert (await pms_lifecycle.process_reservation_version(archive.TENANT, current))["success"]
    assert await database[subject.COLLECTION].count_documents({}) == 2
    assert await database.audit_logs.count_documents({"action": subject.ACTION}) == 2


async def test_parallel_workers_record_no_duplicate_receipts(scenario):
    current = await incoming(scenario.db)
    results = await asyncio.gather(*(pms_lifecycle.process_reservation_version(archive.TENANT, deepcopy(current)) for _ in range(2)))
    assert any(row["success"] for row in results)
    assert await scenario.db[subject.COLLECTION].count_documents({}) == 2
    assert await scenario.db.audit_logs.count_documents({"action": subject.ACTION}) == 2


async def test_new_confirmed_version_cannot_resurrect_reviewed_archive_or_update_guest(scenario):
    current = await incoming(scenario.db, status="confirmed")
    before = await snapshot(scenario.db)
    result = await pms_lifecycle.process_reservation_version(archive.TENANT, current)
    assert result["reason"] == subject.BLOCKED
    assert await snapshot(scenario.db) == before
    assert await scenario.db[subject.COLLECTION].count_documents({}) == 0


async def test_archived_second_room_blocks_entire_modification_before_guest_writes(scenario):
    current = await incoming(scenario.db, status="confirmed")
    first = current["room_stay_lineage"][0]["pms_booking_id"]
    await scenario.db.bookings.update_one({"id": first}, {"$set": {"status": "confirmed", "allocation_source": "channel"},
        "$unset": {"presentation_archive": ""}})
    before = await snapshot(scenario.db)
    assert (await pms_lifecycle.process_reservation_version(archive.TENANT, current))["reason"] == subject.BLOCKED
    assert await snapshot(scenario.db) == before


async def test_other_tenant_or_mismatched_source_cannot_use_known_archive_receipt(scenario):
    current = await incoming(scenario.db)
    bid = next(iter(subject.REVIEWED))
    with pytest.raises(RuntimeError, match=subject.BLOCKED):
        await subject.record_cancellation(scenario.db, "another-tenant", bid, "version", {})
    # A known ID is not sufficient: its exact source group must match as well.
    claim = await pms_lifecycle._acquire_processing_claim(current["provider_version_identity"])
    with pytest.raises(RuntimeError, match=subject.BLOCKED):
        await subject.record_cancellation(scenario.db, archive.TENANT, bid,
            current["provider_version_key"], pms_lifecycle._owned_claim_query(claim))
    assert await scenario.db[subject.COLLECTION].count_documents({}) == 0


async def test_preview_is_get_only_and_separates_readiness_from_recorded_cancellation(scenario):
    database = scenario.db
    for external in sorted(set(subject.REVIEWED.values())):
        await incoming(database, external)
        # A provider cancellation is pending, not a fresh cancellation target.
    before = await snapshot(database)
    pending = await subject.preview(database, archive.TENANT)
    assert not any(row["ready_for_provider_review"] or row["cancellation_recorded"] for row in pending["sources"])
    first = sorted(set(subject.REVIEWED.values()))[0]
    current = await database.exely_reservations.find_one({"external_id": first}, {"_id": 0})
    assert (await pms_lifecycle.process_reservation_version(archive.TENANT, current))["success"]
    for external in sorted(set(subject.REVIEWED.values()))[1:]:
        await database.exely_reservations.update_one({"external_id": external}, {"$set": {"state": "confirmed"}})
    preview = await subject.preview(database, archive.TENANT)
    assert sum(row["ready_for_provider_review"] for row in preview["sources"]) == 2
    assert sum(row["cancellation_recorded"] for row in preview["sources"]) == 1
    assert preview["provider_write_count"] == 0 and not preview["provider_terms_accepted"] and not preview["fee_verified"]
    assert await snapshot(database) == before
    assert await database[subject.COLLECTION].count_documents({}) == 2


@pytest.mark.parametrize("role,tenant,status", [("admin", archive.TENANT, 200), ("reception", archive.TENANT, 403),
    ("housekeeping", archive.TENANT, 403), ("admin", "another-tenant", 404)])
async def test_preview_http_authorization_and_tenant_scope(scenario, monkeypatch, role, tenant, status):
    monkeypatch.setattr(api, "db", scenario.db)
    user = SimpleNamespace(id="operator", tenant_id=tenant, role=role, is_super_admin=False, user_type="hotel")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: user
    before = await snapshot(scenario.db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        result = await client.get("/api/pms/demo-presentation-archive/provider-cancellation-preview")
    assert result.status_code == status
    if status != 200:
        assert "20261110-501694" not in result.text
    assert await snapshot(scenario.db) == before
    assert await scenario.db[subject.COLLECTION].count_documents({}) == 0


@pytest.mark.parametrize("change", ["missing_connection", "business_date"])
async def test_preview_scope_guard_is_conflict_not_internal_error(scenario, monkeypatch, change):
    if change == "missing_connection":
        await scenario.db.exely_connections.delete_many({})
    else:
        await scenario.db.tenant_settings.update_one({"tenant_id": archive.TENANT}, {"$set": {"business_date": "2026-10-27"}})
    monkeypatch.setattr(api, "db", scenario.db)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = actor
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        response = await client.get("/api/pms/demo-presentation-archive/provider-cancellation-preview")
    assert response.status_code == 409
    assert await scenario.db[subject.COLLECTION].count_documents({}) == 0
