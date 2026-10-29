"""Offline regressions for the supported legacy Exely rate update endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from domains.channel_manager import rate_manager_router as router


@pytest.fixture
def scoped_router(monkeypatch):
    mapping = {
        "exely_room_code": "panel-room", "exely_rate_plan_code": "panel-rate",
        "pms_api_room_code": "wire-room", "pms_api_rate_plan_code": "wire-rate",
        "sync_price": True, "sync_availability": True, "sync_restrictions": True,
    }
    calendar = SimpleNamespace(bulk_write=AsyncMock())
    mappings = SimpleNamespace(find=MagicMock(return_value=SimpleNamespace(
        to_list=AsyncMock(return_value=[mapping]),
    )))
    monkeypatch.setattr(router, "db", SimpleNamespace(
        exely_connections=SimpleNamespace(find_one=AsyncMock(return_value={
            "hotel_code": "test-property", "currency": "USD",
        })), exely_room_mappings=mappings, rate_calendar=calendar,
    ))
    queue = AsyncMock(return_value={"accepted": True, "provider_write_count": 0})
    monkeypatch.setattr(router, "enqueue_exely_ari_update", queue)
    monkeypatch.setattr(router, "get_tenant_currency", AsyncMock(return_value=("USD", "$")))
    return SimpleNamespace(mapping=mapping, calendar=calendar, mappings=mappings,
                           queue=queue, user=SimpleNamespace(tenant_id="test-tenant", id="operator"))


async def submit(env, *, bulk, **values):
    common = dict(start_date="2026-11-10", end_date="2026-11-12", **values)
    if bulk:
        fields = [key for key in values if key != "selected_days"]
        request = router.BulkGridUpdateRequest(
            room_type_codes=["panel-room"], rate_plan_codes=["panel-rate"],
            update_fields=fields, **common,
        )
        return await router.bulk_grid_update(request, env.user, None)
    request = router.BulkRateUpdateRequest(updates=[router.RateUpdateRequest(
        room_type_code="panel-room", rate_plan_code="panel-rate", **common,
    )])
    return await router.update_rates(request, env.user, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_wire_aliases_are_used_but_calendar_keeps_panel_keys(scoped_router, bulk):
    env = scoped_router
    await submit(env, bulk=bulk, rate=111)
    call = env.queue.await_args
    assert call.args[:2] == ("test-tenant", "test-property")
    assert call.kwargs["room_type_code"] == "wire-room"
    assert call.kwargs["rate_plan_code"] == "wire-rate"
    assert call.kwargs["currency"] == "USD"
    operations = env.calendar.bulk_write.await_args.args[0]
    assert all(op._filter["room_type_code"] == "panel-room" for op in operations)
    assert env.mappings.find.call_args.args[0] == {"tenant_id": "test-tenant"}


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_partial_api_alias_never_queues_a_mixed_pair(scoped_router, bulk):
    env = scoped_router
    env.mapping["pms_api_rate_plan_code"] = ""
    result = await submit(env, bulk=bulk, rate=111)
    env.queue.assert_not_awaited()
    assert not result["all_queued"]
    assert result["provider_write_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_legacy_mapping_without_api_alias_keeps_its_explicit_pair(scoped_router, bulk):
    env = scoped_router
    env.mapping.pop("pms_api_room_code")
    env.mapping.pop("pms_api_rate_plan_code")
    await submit(env, bulk=bulk, rate=111)
    assert env.queue.await_args.kwargs["room_type_code"] == "panel-room"
    assert env.queue.await_args.kwargs["rate_plan_code"] == "panel-rate"


@pytest.mark.asyncio
async def test_single_update_persists_every_restriction_it_queues(scoped_router):
    env = scoped_router
    await submit(env, bulk=False, max_stay=4, cta=False, ctd=True)
    for op in env.calendar.bulk_write.await_args.args[0]:
        assert {k: op._doc["$set"].get(k) for k in ("max_stay", "cta", "ctd")} == {
            "max_stay": 4, "cta": False, "ctd": True,
        }


@pytest.mark.asyncio
async def test_weekday_filter_applies_to_provider_ranges_as_well_as_local_calendar(scoped_router):
    env = scoped_router
    await submit(env, bulk=True, rate=111, selected_days=[2, 4])  # Tuesday, Thursday
    assert [(c.kwargs["start_date"], c.kwargs["end_date"]) for c in env.queue.await_args_list] == [
        ("2026-11-10", "2026-11-10"), ("2026-11-12", "2026-11-12"),
    ]
    assert [op._filter["date"] for op in env.calendar.bulk_write.await_args.args[0]] == [
        "2026-11-10", "2026-11-12",
    ]


@pytest.mark.asyncio
async def test_no_matching_weekday_cannot_queue_an_unsaved_provider_range(scoped_router):
    env = scoped_router
    await submit(env, bulk=True, rate=111, selected_days=[0])
    env.calendar.bulk_write.assert_not_awaited()
    env.queue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_disabled_sync_dimensions_cannot_leak_in_a_sibling_update(scoped_router, bulk):
    env = scoped_router
    env.mapping.update(sync_availability=False, sync_restrictions=False)
    await submit(env, bulk=bulk, rate=111, availability=6, stop_sell=True, max_stay=4)
    call = env.queue.await_args.kwargs
    assert call["rate_amount"] == 111
    assert all(call[key] is None for key in ("availability", "stop_sell", "max_los"))


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_missing_mapping_does_not_authorize_discovered_panel_codes(scoped_router, bulk):
    env = scoped_router
    env.mappings.find.return_value.to_list.return_value = []
    result = await submit(env, bulk=bulk, rate=111)
    env.queue.assert_not_awaited()
    assert not result["all_queued"]


@pytest.mark.asyncio
async def test_adjacent_selected_days_are_compacted_instead_of_sent_per_day(scoped_router):
    env = scoped_router
    await submit(env, bulk=True, stop_sell=False, selected_days=[2, 3])
    env.queue.assert_awaited_once()
    assert env.queue.await_args.kwargs["start_date"] == "2026-11-10"
    assert env.queue.await_args.kwargs["end_date"] == "2026-11-11"
    assert env.queue.await_args.kwargs["stop_sell"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_queue_runs_only_after_the_calendar_write_is_durable(scoped_router, bulk):
    env = scoped_router

    async def queue(*_args, **_kwargs):
        assert env.calendar.bulk_write.await_count == 1
        return {"accepted": True, "provider_write_count": 0}

    env.queue.side_effect = queue
    result = await submit(env, bulk=bulk, rate=111)
    assert result["all_queued"]
    assert result["all_pushed"] is False and result["provider_write_count"] == 0
