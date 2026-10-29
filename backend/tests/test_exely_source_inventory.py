"""Synthetic/in-memory only: provider-origin inventory after definitive ACK."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import outbox_configuration, outbox_dispatcher
from core.outbox_service import EXELY_RESERVATION_INVENTORY
from domains.channel_manager.providers.exely import lifecycle, pms_lifecycle
from domains.channel_manager.providers.exely import reservation_inventory as inventory
from tests.test_exely_reservation_lifecycle import _add_mapping, _canonical, _persist, _room
from tests.test_exely_reservation_lifecycle import fake_db as fake_db

pytestmark = pytest.mark.exely_failure_stress


def span(kind="Standard", start="2030-01-01", end="2030-01-03"):
    return {"room_type": kind, "date_from": start, "date_to": end}


@pytest.mark.parametrize("before,after,expected", [
    ([], [span()], [span()]),
    ([span()], [], [span()]),
    ([span()], [span()], []),
    ([span(), span()], [span()], [span()]),
    ([span()], [span(end="2030-01-04")], [span(start="2030-01-03", end="2030-01-04")]),
    ([span(end="2030-01-04")], [span()], [span(start="2030-01-03", end="2030-01-04")]),
    ([span()], [span("Deluxe")], [span("Deluxe"), span()]),
    ([span(), span("Deluxe")], [span()], [span("Deluxe")]),
    ([span(end="2030-01-02")], [span(start="2030-01-03", end="2030-01-04")],
     [span(end="2030-01-02"), span(start="2030-01-03", end="2030-01-04")]),
])
def test_only_changed_category_nights_are_planned(before, after, expected):
    assert inventory.changed_ranges(before, after) == expected


async def armed(database):
    await database.exely_connections.insert_one({"tenant_id": "tenant", "hotel_code": "property",
        "is_active": True, "ari_write_enabled": True})


@pytest.mark.asyncio
async def test_physical_assignment_precedes_stale_category_without_source_edits(fake_db):
    await fake_db.rooms.insert_one({"tenant_id": "tenant", "id": "assigned", "room_type": "Standard"})
    row = {"tenant_id": "tenant", "id": "booking", "room_id": "assigned", "room_type": "Deluxe",
        "status": "confirmed", "check_in": "2030-01-01", "check_out": "2030-01-03"}
    await fake_db.bookings.insert_one(row)
    assert await inventory.footprints(fake_db, "tenant", ["booking"]) == [span()]
    assert fake_db.bookings.documents == [row]


@pytest.mark.asyncio
async def test_ambiguous_duplicate_booking_projection_fails_closed(fake_db):
    row = {"tenant_id": "tenant", "id": "booking", "room_id": None, "room_type": "Standard",
        "status": "confirmed", "check_in": "2030-01-01", "check_out": "2030-01-03"}
    fake_db.bookings.documents = [row, deepcopy(row)]
    with pytest.raises(ValueError, match="EXELY_INVENTORY_SOURCE_AMBIGUOUS"):
        await inventory.footprints(fake_db, "tenant", ["booking"])


async def apply(database, canonical, name):
    _, current = await _persist(database, canonical, payload_hash=name,
        event_type="cancellation" if canonical["status"] == "cancelled" else "modification")
    result = await pms_lifecycle.process_reservation_version("tenant", current)
    assert result["success"], result
    current = await database.exely_reservations.find_one(
        {"provider_version_identity": current["provider_version_identity"]}, {"_id": 0})
    version = await database.exely_reservation_versions.find_one(
        {"version_identity": current["provider_version_identity"]}, {"_id": 0})
    return current, version


@pytest.mark.asyncio
async def test_create_contact_extend_shorten_category_partial_full_cancel(fake_db):
    await armed(fake_db)
    await _add_mapping(fake_db)
    await _add_mapping(fake_db, room="DLX", pms="Deluxe")
    rooms = [_room(), _room("2", "DLX")]
    _, v = await apply(fake_db, _canonical(rooms=rooms), "create")
    assert v["inventory_targets_v1"] == [span("Deluxe"), span()]
    _, v = await apply(fake_db, _canonical("2030-01-01T10:01:00Z", rooms=rooms), "contact-only")
    assert v["inventory_targets_v1"] == []
    extended = deepcopy(rooms)
    extended[0]["check_out"] = "2030-01-04T12:00:00"
    _, v = await apply(fake_db, _canonical("2030-01-01T10:02:00Z", rooms=extended), "extend")
    assert v["inventory_targets_v1"] == [span(start="2030-01-03", end="2030-01-04")]
    _, v = await apply(fake_db, _canonical("2030-01-01T10:03:00Z", rooms=rooms), "shorten")
    assert v["inventory_targets_v1"] == [span(start="2030-01-03", end="2030-01-04")]
    changed = deepcopy(rooms)
    changed[0]["room_type_code"] = "DLX"
    _, v = await apply(fake_db, _canonical("2030-01-01T10:04:00Z", rooms=changed), "change-category")
    assert v["inventory_targets_v1"] == [span("Deluxe"), span()]
    _, v = await apply(fake_db, _canonical("2030-01-01T10:05:00Z", rooms=[changed[0]]), "partial-cancel")
    assert v["inventory_targets_v1"] == [span("Deluxe")]
    _, v = await apply(fake_db, _canonical("2030-01-01T10:06:00Z", rooms=[changed[0]], status="cancelled"), "full-cancel")
    assert v["inventory_targets_v1"] == [span("Deluxe")]


@pytest.mark.asyncio
@pytest.mark.parametrize("ack_result", [None, False])
async def test_failed_or_ambiguous_ack_never_queues_inventory(fake_db, monkeypatch, ack_result):
    await armed(fake_db)
    await _add_mapping(fake_db)
    current, _ = await apply(fake_db, _canonical(), "create")
    queued = AsyncMock()
    monkeypatch.setattr(inventory, "enqueue_outbox_event", queued)
    confirm = AsyncMock(side_effect=TimeoutError()) if ack_result is None else AsyncMock(
        return_value=SimpleNamespace(success=False, error_type="ProviderRejected"))
    result = await lifecycle.acknowledge_durable_version(SimpleNamespace(confirm_delivery=confirm), current)
    assert not result["success"]
    queued.assert_not_awaited()
    await lifecycle.acknowledge_durable_version(SimpleNamespace(confirm_delivery=confirm), current)
    assert confirm.await_count == 1


@pytest.mark.asyncio
async def test_ack_success_local_enqueue_failure_recovers_without_second_ack(fake_db, monkeypatch):
    await armed(fake_db)
    await _add_mapping(fake_db)
    current, _ = await apply(fake_db, _canonical(), "create")
    queued = AsyncMock(side_effect=[RuntimeError("synthetic local failure"), {"id": "local-event"}])
    monkeypatch.setattr(inventory, "enqueue_outbox_event", queued)
    provider = SimpleNamespace(confirm_delivery=AsyncMock(return_value=SimpleNamespace(success=True)))
    assert (await lifecycle.acknowledge_durable_version(provider, current))["success"]
    assert (await lifecycle.acknowledge_pending_versions(provider, "tenant"))["failed"] == 0
    assert queued.await_count == 2
    assert queued.await_args_list[0].kwargs["idempotency_key"] == queued.await_args_list[1].kwargs["idempotency_key"]
    provider.confirm_delivery.assert_awaited_once()
    await lifecycle.acknowledge_durable_version(provider, current)
    assert queued.await_count == 2


@pytest.mark.asyncio
async def test_off_at_ingestion_is_never_historical_backfill(fake_db, monkeypatch):
    await _add_mapping(fake_db)
    current, version = await apply(fake_db, _canonical(), "off-create")
    assert version["inventory_before_v1"]["armed"] is False
    assert version["inventory_targets_v1"] == []
    await armed(fake_db)
    queued = AsyncMock()
    monkeypatch.setattr(inventory, "enqueue_outbox_event", queued)
    provider = SimpleNamespace(confirm_delivery=AsyncMock(return_value=SimpleNamespace(success=True)))
    assert (await lifecycle.acknowledge_durable_version(provider, current))["success"]
    queued.assert_not_awaited()
    # Pre-deployment ACKed versions have no inventory marker and are never backfilled.
    await inventory.enqueue_after_ack(fake_db, {"tenant_id": "tenant", "ack_state": "ACKED"})
    queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_definitive_version_ack_recovers_local_crash_without_resending(fake_db, monkeypatch):
    await armed(fake_db)
    await _add_mapping(fake_db)
    current, version = await apply(fake_db, _canonical(), "create")
    await fake_db.exely_reservation_versions.update_one(
        {"version_identity": version["version_identity"]}, {"$set": {"ack_state": "ACKED", "acked_at": "2030-01-01T10:00:01Z"}})
    await fake_db.exely_reservations.update_one(
        {"provider_version_identity": version["version_identity"]}, {"$set": {"delivery_state": lifecycle.ACK_SENDING}})
    queued = AsyncMock()
    monkeypatch.setattr(inventory, "enqueue_outbox_event", queued)
    provider = SimpleNamespace(confirm_delivery=AsyncMock())
    assert (await lifecycle.acknowledge_pending_versions(provider, "tenant"))["failed"] == 0
    queued.assert_awaited_once()
    provider.confirm_delivery.assert_not_awaited()
    stored = await fake_db.exely_reservations.find_one({"provider_version_identity": current["provider_version_identity"]})
    assert stored["delivery_state"] == "ACKED" and stored["delivery_confirmed"] is True


@pytest.mark.asyncio
async def test_retry_uses_original_before_image_after_partial_booking_write(fake_db, monkeypatch):
    await armed(fake_db)
    await _add_mapping(fake_db)
    await _add_mapping(fake_db, room="DLX", pms="Deluxe")
    _, current = await _persist(fake_db, _canonical(rooms=[_room(), _room("2", "DLX")]))
    original = pms_lifecycle._upsert_booking
    count = 0

    async def fail_second(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("synthetic crash after first booking")
        return await original(*args)

    monkeypatch.setattr(pms_lifecycle, "_upsert_booking", fail_second)
    assert not (await pms_lifecycle.process_reservation_version("tenant", current))["success"]
    assert len(fake_db.bookings.documents) == 1
    monkeypatch.setattr(pms_lifecycle, "_upsert_booking", original)
    assert (await pms_lifecycle.process_reservation_version("tenant", current))["success"]
    version = await fake_db.exely_reservation_versions.find_one({"version_identity": current["provider_version_identity"]})
    assert version["inventory_before_v1"]["footprints"] == []
    assert version["inventory_targets_v1"] == [span("Deluxe"), span()]


async def event_fixture(database):
    await armed(database)
    await _add_mapping(database)
    _, version = await apply(database, _canonical(), "create")
    await database.exely_reservation_versions.update_one(
        {"version_identity": version["version_identity"]}, {"$set": {"ack_state": "ACKED"}})
    return {"tenant_id": "tenant", "event_type": EXELY_RESERVATION_INVENTORY,
        "provider": "exely", "property_id": "property", "entity_id": version["version_identity"],
        "payload": {"version_identity": version["version_identity"], "targets": version["inventory_targets_v1"]}}


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["foreign-tenant", "wrong-provider", "wrong-property", "wrong-entity", "extra-date", "no-ack", "disabled", "archived", "deleted"])
async def test_source_scope_or_gate_failure_prevents_dispatch(fake_db, mutation):
    event = await event_fixture(fake_db)
    if mutation == "foreign-tenant":
        event["tenant_id"] = "other"
    elif mutation == "wrong-provider":
        event["provider"] = "hotelrunner"
    elif mutation == "wrong-property":
        event["property_id"] = "other"
    elif mutation == "wrong-entity":
        event["entity_id"] = "other"
    elif mutation == "extra-date":
        event["payload"]["targets"][0]["date_to"] = "2030-02-01"
    elif mutation == "no-ack":
        fake_db.exely_reservation_versions.documents[0]["ack_state"] = lifecycle.ACK_PENDING
    elif mutation == "disabled":
        fake_db.exely_connections.documents[0]["ari_write_enabled"] = False
    elif mutation == "archived":
        fake_db.bookings.documents[0]["status"] = "archived_demo"
    else:
        fake_db.bookings.documents.clear()
    with pytest.raises(ValueError):
        await inventory.checked_event(fake_db, event)


@pytest.mark.asyncio
async def test_dispatch_recomputes_current_category_and_bypasses_fanout(fake_db, monkeypatch):
    event = await event_fixture(fake_db)
    monkeypatch.setattr("core.database.db", fake_db)
    monkeypatch.setattr("domains.channel_manager.providers.exely.production_safety.ari_write_block_reason", lambda: None)
    canonical = AsyncMock(return_value={"2030-01-01": 8, "2030-01-02": 8})
    push = AsyncMock(return_value={"queued_operations": 1, "errors": []})
    monkeypatch.setattr("domains.channel_manager.availability_auto_sync._load_authoritative_availability", canonical)
    monkeypatch.setattr("domains.channel_manager.availability_auto_sync._push_to_exely", push)
    fanout = AsyncMock()
    monkeypatch.setattr("core.agency_fanout.fan_out_agency_events", fanout)
    ok, _ = await outbox_dispatcher.dispatch_outbox_event(event)
    assert ok
    assert canonical.await_args.args[:2] == ("tenant", "Standard")
    assert push.await_args.args == ("tenant", "Standard", {"2030-01-01": 8, "2030-01-02": 8})
    fanout.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_second_mapping_blocks_every_target_before_inventory_work(fake_db, monkeypatch):
    event = await event_fixture(fake_db)
    target = span("Deluxe")
    event["payload"]["targets"].append(target)
    fake_db.exely_reservation_versions.documents[0]["inventory_targets_v1"].append(target)
    monkeypatch.setattr("core.database.db", fake_db)
    monkeypatch.setattr("domains.channel_manager.providers.exely.production_safety.ari_write_block_reason", lambda: None)
    canonical, push = AsyncMock(), AsyncMock()
    monkeypatch.setattr("domains.channel_manager.availability_auto_sync._load_authoritative_availability", canonical)
    monkeypatch.setattr("domains.channel_manager.availability_auto_sync._push_to_exely", push)
    ok, message = await inventory.dispatch(event)
    assert not ok and "exely_room_mapping_missing" in message
    canonical.assert_not_awaited()
    push.assert_not_awaited()
    monkeypatch.setattr(outbox_configuration, "db", fake_db)
    ready = await outbox_configuration.booking_configuration_readiness(event)
    assert ready == {"ready": False, "issues": ["exely_room_mapping_missing"], "providers": ["exely"]}


@pytest.mark.asyncio
async def test_runtime_kill_switch_stops_before_any_source_read(fake_db, monkeypatch):
    checked = AsyncMock()
    monkeypatch.setattr(inventory, "checked_event", checked)
    monkeypatch.setattr("domains.channel_manager.providers.exely.production_safety.ari_write_block_reason", lambda: "EXELY_ARI_DISABLED")
    assert await inventory.dispatch({}) == (False, "permanent: EXELY_ARI_DISABLED")
    checked.assert_not_awaited()
