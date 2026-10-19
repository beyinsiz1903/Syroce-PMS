from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from core import outbox_configuration as module
from routers import outbox_admin


def event():
    return {"id": "event", "tenant_id": "hotel", "status": "failed", "event_type": "booking.cancelled.v1",
            "last_error": "retryable: legacy channel availability sync failed: exely_room_mapping_missing",
            "payload": {"room_id": "room", "check_in": "2026-11-20", "check_out": "2026-11-22"}}


def test_mapping_guard_is_scoped_to_booking_availability_events():
    assert module.is_configuration_failure(event())
    unrelated = {**event(), "event_type": "agency.webhook.v1", "last_error": "invalid_date_range"}
    assert not module.is_configuration_failure(unrelated)


@pytest.fixture
def database(monkeypatch):
    def collection(rows):
        return SimpleNamespace(find=MagicMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=rows))))

    db = SimpleNamespace(
        rooms=SimpleNamespace(find_one=AsyncMock(return_value={"room_type": "Standard"})),
        exely_connections=SimpleNamespace(find_one=AsyncMock(return_value={"hotel_code": "hotel-wire"})),
        exely_room_mappings=collection([]),
        hotelrunner_connections=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        hotelrunner_room_mappings=collection([]),
    )
    monkeypatch.setattr(module, "db", db)
    return db


@pytest.mark.asyncio
async def test_readiness_is_tenant_scoped_and_missing_mapping_is_not_ready(database):
    result = await module.booking_configuration_readiness(event())
    assert not result["ready"] and result["issues"] == ["exely_room_mapping_missing"]
    database.rooms.find_one.assert_awaited_once_with({"tenant_id": "hotel", "id": "room"}, {"_id": 0, "room_type": 1})
    assert database.exely_room_mappings.find.call_args.args[0]["tenant_id"] == "hotel"
    # The fake collections deliberately expose no writes or external calls.


@pytest.mark.asyncio
@pytest.mark.parametrize("mappings,issue", [
    ([{}], "exely_room_mapping_incomplete"),
    ([{"exely_room_code": "a", "exely_rate_plan_code": "x"}, {"exely_room_code": "b", "exely_rate_plan_code": "y"}], "exely_multiple_availability_mappings"),
])
async def test_incomplete_or_ambiguous_exely_mapping_stays_blocked(database, mappings, issue):
    database.exely_room_mappings.find.return_value.to_list.return_value = mappings
    result = await module.booking_configuration_readiness(event())
    assert result["issues"] == [issue]


@pytest.mark.asyncio
async def test_corrected_wire_pair_can_be_rechecked_without_dispatch(database):
    database.exely_room_mappings.find.return_value.to_list.return_value = [
        {"pms_api_room_code": "room-wire", "pms_api_rate_plan_code": "rate-wire"}]
    result = await module.booking_configuration_readiness(event())
    assert result == {"ready": True, "issues": [], "providers": ["exely"]}


@pytest.mark.asyncio
async def test_disabled_connection_is_not_proof_of_delivery(database):
    database.exely_connections.find_one.return_value = None
    result = await module.booking_configuration_readiness(event())
    assert not result["ready"] and "no_active_provider_connection" in result["issues"]


@pytest.mark.asyncio
async def test_other_active_provider_cannot_hide_original_failed_target(database):
    database.exely_connections.find_one.return_value = None
    database.hotelrunner_connections.find_one.return_value = {"id": "hotelrunner"}
    database.hotelrunner_room_mappings.find.return_value.to_list.return_value = [{"hr_inv_code": "room-wire"}]
    result = await module.booking_configuration_readiness(event())
    assert result == {"ready": False, "issues": ["exely_connection_inactive"], "providers": ["hotelrunner"]}


@pytest.mark.asyncio
async def test_malformed_dates_cannot_pass_preflight(database):
    document = event()
    document["payload"]["check_out"] = "2026-11-19"
    assert (await module.booking_configuration_readiness(document))["issues"] == ["invalid_date_range"]
    database.rooms.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_requeue_does_not_modify_event_until_configuration_is_fixed(monkeypatch):
    events = SimpleNamespace(find_one=AsyncMock(return_value=event()), find_one_and_update=AsyncMock())
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    monkeypatch.setattr(outbox_admin, "booking_configuration_readiness", AsyncMock(return_value={"ready": False, "issues": ["exely_room_mapping_missing"]}))
    with pytest.raises(HTTPException) as exc:
        await outbox_admin.requeue_event("event")
    assert exc.value.status_code == 409
    events.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_requeue_after_repair_preserves_old_error_and_compares_observed_record(monkeypatch):
    events = SimpleNamespace(find_one=AsyncMock(return_value=event()), find_one_and_update=AsyncMock(return_value={"id": "event"}))
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    monkeypatch.setattr(outbox_admin, "booking_configuration_readiness", AsyncMock(return_value={"ready": True, "issues": []}))
    assert (await outbox_admin.requeue_event("event")).success
    query, update = events.find_one_and_update.call_args.args
    assert query["tenant_id"] == "hotel" and query["last_error"] == event()["last_error"]
    assert update["$set"]["requeue_previous_error"] == event()["last_error"]


@pytest.mark.asyncio
async def test_bulk_replay_does_not_bypass_configuration_guard(monkeypatch):
    events = SimpleNamespace(count_documents=AsyncMock(return_value=2), update_many=AsyncMock(return_value=SimpleNamespace(modified_count=1)))
    monkeypatch.setattr(outbox_admin, "db", SimpleNamespace(outbox_events=events))
    result = await outbox_admin.replay_failed_events(provider="exely", tenant_id="hotel")
    assert result.requeued_count == 1 and result.blocked_count == 2
    query = events.update_many.call_args.args[0]
    assert query["tenant_id"] == "hotel" and query["provider"] == "exely"
    excluded = query["$nor"][0]
    assert excluded["last_error"]["$regex"] == module.CONFIGURATION_ERROR_PATTERN
    assert excluded["event_type"]["$in"] == list(module.BOOKING_AVAILABILITY_EVENTS)
