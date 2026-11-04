"""Offline editor -> calendar -> mapped SOAP -> readback regressions."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from lxml import etree
from pydantic import ValidationError

from domains.channel_manager import remaining_availability
from domains.channel_manager import unified_rate_manager_router as router
from domains.channel_manager.calendar_inventory import exely_publishable_availability
from domains.channel_manager.providers.exely import ari_delivery
from domains.channel_manager.providers.exely.ari_delivery import deliver_exely_ari
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.provider_quota import ExelyProviderQuota
from domains.channel_manager.providers.exely.soap_builder import build_availability_batch_rq

TENANT = "synthetic-hotel"
ROOM = "panel-standard"
RATE = "panel-base"
DAYS = ["2026-11-10", "2026-11-11", "2026-11-12"]


def cursor(rows):
    return SimpleNamespace(to_list=AsyncMock(side_effect=lambda limit: deepcopy(rows[:limit])))


@pytest.fixture
def editor(monkeypatch):
    mappings = [{
        "tenant_id": TENANT, "pms_room_type": "Standard", "exely_room_code": ROOM,
        "exely_rate_plan_code": RATE, "pms_api_room_code": "soap-standard",
        "pms_api_rate_plan_code": "soap-base", "sync_availability": True,
        "sync_price": True, "sync_restrictions": True,
    }]
    rooms = [{"id": f"room-{i}", "room_type": "Standard", "status": "available"} for i in range(8)]
    bookings = [
        {"room_id": "room-0", "room_type": "Standard", "check_in": "2026-11-10", "check_out": "2026-11-13"},
        {"room_id": "room-1", "room_type": "Standard", "check_in": "2026-11-11", "check_out": "2026-11-12"},
    ]
    locks = []
    calendar = [{"tenant_id": TENANT, "room_type_code": ROOM, "rate_plan_code": RATE, "date": day,
                 "availability": 8, "rate": 100, "min_stay": 2, "stop_sell": False} for day in DAYS]

    def scoped_find(rows):
        def find(query, projection):
            assert query["tenant_id"] == TENANT
            return cursor(rows)
        return MagicMock(side_effect=find)

    async def save(operations, **kwargs):
        for op in operations:
            assert op._filter["tenant_id"] == TENANT
            row = next((r for r in calendar if all(r.get(k) == v for k, v in op._filter.items())), None)
            if row is None:
                row = dict(op._filter)
                calendar.append(row)
            row.update(op._doc["$set"])

    cal = SimpleNamespace(find=scoped_find(calendar), bulk_write=AsyncMock(side_effect=save))
    database = MagicMock()
    database.rooms = SimpleNamespace(find=scoped_find(rooms))
    database.bookings = SimpleNamespace(find=scoped_find(bookings))
    database.room_night_locks = SimpleNamespace(find=scoped_find(locks))
    database.exely_room_mappings = SimpleNamespace(find=scoped_find(mappings))
    database.room_mappings = SimpleNamespace(find=scoped_find([]))
    database.hotelrunner_connections = SimpleNamespace(find_one=AsyncMock(return_value=None))
    database.pricing_settings = SimpleNamespace(find=scoped_find([]))
    database.rate_calendar = cal
    database.__getitem__.side_effect = lambda key: cal if key == "rate_calendar" else (_ for _ in ()).throw(AssertionError(key))
    connection = {"hotel_code": "synthetic-property", "ari_write_enabled": True, "currency": "USD"}
    monkeypatch.setattr(router, "db", database)
    monkeypatch.setattr(router, "_detect_active_provider", AsyncMock(return_value={"provider": "exely", "connection": connection}))
    monkeypatch.setattr(router, "require_tenant_module", AsyncMock())
    monkeypatch.setattr(router, "_ari_write_block_for_targets", lambda *_: "")
    monkeypatch.setattr(router, "get_tenant_currency", AsyncMock(return_value=("USD", {})))
    provider = AsyncMock(return_value=ari_delivery.ExelyARIDeliveryResult(True, "confirmed", "", "SUCCESS", 1, "synthetic-write"))
    monkeypatch.setattr(ari_delivery, "deliver_exely_ari", provider)
    return SimpleNamespace(db=database, calendar=calendar, save=cal.bulk_write, mappings=mappings,
                           bookings=bookings, locks=locks, provider=provider, connection=connection)


def request(net=3, **overrides):
    return router.RemainingBulkUpdateRequest(**{
        "per_room_values": [{"room_type_code": ROOM, "rate_plan_codes": [RATE], "availability": net}],
        "start_date": DAYS[0], "end_date": DAYS[-1], "update_fields": ["availability"], **overrides,
    })


async def apply(payload):
    return await router.unified_remaining_grid_update(payload, SimpleNamespace(tenant_id=TENANT, id="synthetic-operator"), None)


async def readback(editor):
    grid = await router._build_exely_grid(TENANT, editor.connection, DAYS[0], DAYS[-1])
    return grid["grid"][0]["dates"]


async def test_manual_override_can_exceed_old_physical_grid_without_releasing_lock(editor):
    """Physical 7 stays protected, while an explicit sales override may sell 8."""
    day = "2026-12-20"
    editor.bookings.clear()
    editor.calendar[:] = [{**editor.calendar[0], "date": day}]
    editor.locks.append({"room_id": "room-3", "night_date": day, "lock_type": "booking"})
    grid = await router._build_exely_grid(TENANT, editor.connection, day, day)
    cell = grid["grid"][0]["dates"][0]
    assert (cell["base_availability"], cell["sold"], cell["availability"]) == (8, 0, 7)
    await apply(request(8, start_date=day, end_date=day))
    grid = await router._build_exely_grid(TENANT, editor.connection, day, day)
    assert grid["grid"][0]["dates"][0]["availability"] == 8
    assert grid["grid"][0]["dates"][0]["availability_mode"] == "manual_remaining"
    assert len(editor.locks) == 1
    assert editor.provider.await_args.args[2]["value"][0]["availability"] == 8


@pytest.mark.parametrize("kind", ["booking", "hold", "ooo", "oos", "maintenance"])
async def test_grid_honours_each_lock_type_even_without_active_booking_document(editor, kind):
    editor.bookings.clear()
    editor.locks.append({"room_id": "room-0", "night_date": DAYS[1], "lock_type": kind})
    cells = await readback(editor)
    assert [v["availability"] for v in cells] == [8, 7, 8]
    assert [v["sold"] for v in cells] == [0, 0, 0]
    editor.save.assert_not_awaited()
    editor.provider.assert_not_awaited()


async def test_grid_does_not_double_subtract_assigned_booking_lock_but_counts_unassigned(editor):
    editor.bookings[:] = [editor.bookings[0], {**editor.bookings[0], "room_id": None}]
    editor.locks.extend({"room_id": "room-0", "night_date": day, "lock_type": "booking"} for day in DAYS)
    cells = await readback(editor)
    assert [v["availability"] for v in cells] == [6, 6, 6]
    assert [v["sold"] for v in cells] == [2, 2, 2]


async def test_grid_keeps_smaller_commercial_allotment_and_zero(editor):
    editor.calendar[0]["availability"] = 5
    editor.calendar[1]["availability"] = 0
    editor.locks.append({"room_id": "room-6", "night_date": DAYS[0], "lock_type": "hold"})
    cells = await readback(editor)
    assert [v["availability"] for v in cells] == [4, 0, 7]
    assert [v["base_availability"] for v in cells] == [5, 0, 8]


async def test_grid_full_lock_window_is_one_tenant_scoped_query_for_all_plans(editor):
    editor.mappings.extend({**editor.mappings[0], "exely_rate_plan_code": plan, "sync_availability": False} for plan in ["NONREF", "DYNAMIC"])
    grid = await router._build_exely_grid(TENANT, editor.connection, DAYS[0], DAYS[-1])
    assert len(grid["grid"]) == 3
    find = editor.db.room_night_locks.find
    find.assert_called_once()
    query = find.call_args.args[0]
    assert query["tenant_id"] == TENANT
    assert query["night_date"] == {"$gte": DAYS[0], "$lte": DAYS[-1]}
    assert query["room_id"]["$in"] == [f"room-{i}" for i in range(8)]


@pytest.mark.parametrize("fault", ["unavailable", "duplicate", "unknown_kind", "foreign_room", "truncated"])
async def test_grid_never_reports_false_free_rooms_when_lock_projection_is_incomplete(editor, fault):
    lock = {"room_id": "room-0", "night_date": DAYS[0], "lock_type": "booking"}
    if fault == "unavailable":
        editor.db.room_night_locks.find.side_effect = RuntimeError("synthetic lock store down")
    elif fault == "duplicate":
        editor.locks.extend([lock, deepcopy(lock)])
    elif fault == "truncated":
        editor.locks.extend([lock] * 100001)
    else:
        editor.locks.append({**lock, **({"lock_type": "unknown"} if fault == "unknown_kind" else {"room_id": "foreign"})})
    with pytest.raises(HTTPException) as exc:
        await readback(editor)
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "EXELY_GRID_INVENTORY_UNAVAILABLE"
    editor.save.assert_not_awaited()
    editor.provider.assert_not_awaited()


async def test_net_input_matches_wire_and_readback_with_varying_daily_sales(editor):
    result = await apply(request())
    assert result["availability_input_mode"] == "remaining"
    assert result["provider_verified"] is True
    assert result["saved"] == 3
    cells = await readback(editor)
    assert [v["sold"] for v in cells] == [1, 2, 1]
    assert [v["base_availability"] for v in cells] == [4, 5, 4]
    assert [v["availability"] for v in cells] == [3, 3, 3]
    assert all(v["rate"] == 100 and v["min_stay"] == 2 and v["stop_sell"] is False for v in cells)
    args, kwargs = editor.provider.await_args
    assert args[:2] == (TENANT, "availability_batch")
    assert args[2]["value"] == [{"room_type_code": "soap-standard", "rate_plan_code": "soap-base",
                                  "start_date": DAYS[0], "end_date": DAYS[-1], "availability": 3}]
    assert args[2]["property_id"] == "synthetic-property"
    envelope = etree.fromstring(build_availability_batch_rq("synthetic-user", "synthetic-password", "synthetic-property", args[2]["value"]).encode())
    controls = envelope.findall(".//{http://www.opentravel.org/OTA/2003/05}StatusApplicationControl")
    assert [dict(c.attrib) for c in controls] == [{"Start": DAYS[0], "End": DAYS[-1], "InvTypeCode": "soap-standard", "RatePlanCode": "soap-base"}]
    assert envelope.find(".//{http://www.opentravel.org/OTA/2003/05}AvailStatusMessage").get("BookingLimit") == "3"


async def test_zero_is_preserved_and_same_input_does_not_compound_sold_rooms(editor):
    await apply(request(0))
    await apply(request(0))
    cells = await readback(editor)
    assert [v["base_availability"] for v in cells] == [1, 2, 1]
    assert [v["availability"] for v in cells] == [0, 0, 0]
    assert all(call.args[2]["value"][0]["availability"] == 0 for call in editor.provider.await_args_list)


async def test_later_booking_and_cancellation_adjust_remaining_once(editor):
    await apply(request(3))
    editor.bookings.append({"room_id": "room-2", "room_type": "Standard", "check_in": DAYS[0], "check_out": "2026-11-13"})
    assert [v["availability"] for v in await readback(editor)] == [2, 2, 2]
    auto_values = await exely_publishable_availability(editor.db, TENANT, "Standard", editor.mappings[0],
                                                      dict(zip(DAYS, [6, 5, 6])))
    assert list(auto_values.values()) == [2, 2, 2]
    editor.bookings.pop()
    assert [v["availability"] for v in await readback(editor)] == [3, 3, 3]
    assert list((await exely_publishable_availability(editor.db, TENANT, "Standard", editor.mappings[0],
                                                      dict(zip(DAYS, [7, 6, 7])))).values()) == [3, 3, 3]


@pytest.mark.parametrize("kind", ["booking", "hold", "ooo", "oos", "maintenance"])
async def test_manual_three_is_sent_even_with_zero_physical_capacity_and_keeps_all_locks(editor, kind):
    editor.locks.extend({"room_id": f"room-{i}", "night_date": day, "lock_type": kind}
                        for day in DAYS for i in range(8))
    original_locks, original_bookings = deepcopy(editor.locks), deepcopy(editor.bookings)
    result = await apply(request(3))
    assert result["availability_modes"] == {ROOM: "manual_remaining"}
    assert [v["availability"] for v in await readback(editor)] == [3, 3, 3]
    assert editor.provider.await_args.args[2]["value"][0]["availability"] == 3
    # Booking-driven delivery must not silently clamp an authorized overbook.
    assert list((await exely_publishable_availability(editor.db, TENANT, "Standard", editor.mappings[0],
                                                      dict.fromkeys(DAYS, 0))).values()) == [3, 3, 3]
    assert editor.locks == original_locks and editor.bookings == original_bookings
    editor.bookings.append({"room_id": None, "room_type": "Standard", "check_in": DAYS[0], "check_out": "2026-11-13"})
    assert [v["availability"] for v in await readback(editor)] == [2, 2, 2]
    assert list((await exely_publishable_availability(editor.db, TENANT, "Standard", editor.mappings[0],
                                                      dict.fromkeys(DAYS, 0))).values()) == [2, 2, 2]


async def test_blank_availability_uses_each_nights_actual_capacity_in_one_batch(editor):
    editor.locks.extend({"room_id": f"room-{i}", "night_date": DAYS[1], "lock_type": "hold"} for i in range(8))
    result = await apply(request(None))
    assert result["availability_modes"] == {ROOM: "automatic"}
    assert [v["availability"] for v in await readback(editor)] == [7, 0, 7]
    assert all(row["availability"] is None and row["availability_mode"] == "automatic" for row in editor.calendar)
    editor.provider.assert_awaited_once()
    messages = editor.provider.await_args.args[2]["value"]
    assert [(v["start_date"], v["end_date"], v["availability"]) for v in messages] == [(day, day, n) for day, n in zip(DAYS, [7, 0, 7])]
    envelope = etree.fromstring(build_availability_batch_rq("synthetic", "synthetic", "synthetic-property", messages).encode())
    assert [v.get("BookingLimit") for v in envelope.findall(".//{http://www.opentravel.org/OTA/2003/05}AvailStatusMessage")] == ["7", "0", "7"]


async def test_blank_resets_a_previous_manual_override_and_zero_is_not_blank(editor):
    await apply(request(0))
    assert [v["availability"] for v in await readback(editor)] == [0, 0, 0]
    await apply(request(None))
    assert [v["availability"] for v in await readback(editor)] == [7, 6, 7]
    assert all(v["availability_mode"] == "automatic" for v in await readback(editor))
    assert list((await exely_publishable_availability(editor.db, TENANT, "Standard", editor.mappings[0],
                                                      dict(zip(DAYS, [7, 6, 7])))).values()) == [7, 6, 7]
    assert all(v["rate"] == 100 and v["min_stay"] == 2 and v["stop_sell"] is False for v in editor.calendar)


async def test_two_rooms_can_mix_manual_and_automatic_inventory_in_one_soap_batch(editor):
    editor.mappings.append({**editor.mappings[0], "pms_room_type": "Deluxe",
                            "exely_room_code": "panel-deluxe", "pms_api_room_code": "soap-deluxe"})
    rooms = [{"id": f"room-{i}", "room_type": "Standard", "status": "available"} for i in range(8)]
    rooms.extend({"id": f"deluxe-{i}", "room_type": "Deluxe", "status": "available"} for i in range(8))
    editor.db.rooms.find.side_effect = lambda query, projection: cursor(rooms)
    # Standard is fully locked, but its manual 3 must still be sent. Deluxe
    # uses an unassigned reservation plus one independent maintenance block.
    editor.locks.extend({"room_id": f"room-{i}", "night_date": DAYS[1], "lock_type": "booking"} for i in range(8))
    editor.bookings.append({"room_id": None, "room_type": "Deluxe", "check_in": DAYS[1], "check_out": DAYS[2]})
    editor.locks.append({"room_id": "deluxe-0", "night_date": DAYS[1], "lock_type": "maintenance"})
    def scoped_locks(query, projection):
        assert query["tenant_id"] == TENANT
        return cursor([row for row in editor.locks if row["room_id"] in query["room_id"]["$in"]])
    editor.db.room_night_locks.find.side_effect = scoped_locks
    result = await apply(request(per_room_values=[
        {"room_type_code": ROOM, "rate_plan_codes": [RATE], "availability": 3},
        {"room_type_code": "panel-deluxe", "rate_plan_codes": [RATE], "availability": None},
    ]))
    assert result["availability_modes"] == {ROOM: "manual_remaining", "panel-deluxe": "automatic"}
    editor.provider.assert_awaited_once()
    messages = editor.provider.await_args.args[2]["value"]
    assert [(m["room_type_code"], m["start_date"], m["end_date"], m["availability"]) for m in messages] == [
        ("soap-standard", DAYS[0], DAYS[-1], 3),
        ("soap-deluxe", DAYS[0], DAYS[0], 8), ("soap-deluxe", DAYS[1], DAYS[1], 6), ("soap-deluxe", DAYS[2], DAYS[2], 8),
    ]
    envelope = etree.fromstring(build_availability_batch_rq("synthetic", "synthetic", "synthetic-property", messages).encode())
    assert len(envelope.findall(".//{http://www.opentravel.org/OTA/2003/05}AvailStatusMessages")) == 1
    assert len(envelope.findall(".//{http://www.opentravel.org/OTA/2003/05}AvailStatusMessage")) == 4


async def test_automatic_reset_with_weekday_filter_preserves_unselected_manual_dates(editor):
    await apply(request(3))
    await apply(request(None, selected_days=[3]))  # Only Wednesday 11 November.
    assert [(v["availability"], v["availability_mode"]) for v in await readback(editor)] == [
        (3, "manual_remaining"), (6, "automatic"), (3, "manual_remaining"),
    ]
    assert editor.provider.await_args.args[2]["value"] == [{"room_type_code": "soap-standard", "rate_plan_code": "soap-base",
                                                         "start_date": DAYS[1], "end_date": DAYS[1], "availability": 6}]


@pytest.mark.parametrize("fault", ["duplicate", "unknown_kind", "unavailable"])
async def test_automatic_input_still_fails_closed_for_untrusted_lock_projection(editor, fault):
    lock = {"room_id": "room-0", "night_date": DAYS[1], "lock_type": "booking"}
    if fault == "unavailable":
        editor.db.room_night_locks.find.side_effect = ConnectionError("synthetic outage")
    elif fault == "duplicate":
        editor.locks.extend([lock, deepcopy(lock)])
    else:
        editor.locks.append({**lock, "lock_type": "unknown"})
    original = deepcopy(editor.calendar)
    with pytest.raises(HTTPException) as exc:
        await apply(request(None))
    assert exc.value.status_code == 503 and exc.value.detail["provider_write_count"] == 0
    assert editor.calendar == original
    editor.save.assert_not_awaited()
    editor.provider.assert_not_awaited()


async def test_manual_stock_is_shared_with_non_owner_tariff_without_changing_its_price(editor):
    editor.mappings.append({**editor.mappings[0], "exely_rate_plan_code": "NONREF", "sync_availability": False})
    editor.calendar.extend({**row, "rate_plan_code": "NONREF", "rate": 200, "availability": 0} for row in deepcopy(editor.calendar))
    await apply(request(10))
    grid = await router._build_exely_grid(TENANT, editor.connection, DAYS[0], DAYS[-1])
    assert len(grid["grid"]) == 2
    for row in grid["grid"]:
        assert [v["availability"] for v in row["dates"]] == [10, 10, 10]
        assert all(v["rate"] == (100 if row["rate_plan_code"] == RATE else 200) for v in row["dates"])


async def test_price_only_update_keeps_manual_overbooking_and_a_legacy_inventory_write_clears_it(editor):
    await apply(request(10))
    price_only = router.UnifiedBulkUpdateRequest(**request(rate=120, update_fields=["rate"]).model_dump())
    await router.unified_bulk_grid_update(price_only, SimpleNamespace(tenant_id=TENANT, id="operator"), None)
    assert [v["availability"] for v in await readback(editor)] == [10, 10, 10]
    base_update = router.UnifiedBulkUpdateRequest(**request(5).model_dump())
    await router.unified_bulk_grid_update(base_update, SimpleNamespace(tenant_id=TENANT, id="operator"), None)
    assert [v["availability"] for v in await readback(editor)] == [4, 3, 4]
    assert all(v["availability_mode"] == "legacy" for v in await readback(editor))


async def test_maximum_manual_stock_stays_within_wire_limit_after_a_cancellation(editor):
    await apply(request(999))
    editor.bookings.clear()
    assert [v["availability"] for v in await readback(editor)] == [999, 999, 999]
    assert list((await exely_publishable_availability(editor.db, TENANT, "Standard", editor.mappings[0],
                                                      dict.fromkeys(DAYS, 8))).values()) == [999, 999, 999]


async def test_weekday_filter_never_changes_or_sends_unselected_dates(editor):
    await apply(request(3, selected_days=[3]))  # Wednesday, November 11
    cells = await readback(editor)
    assert [v["base_availability"] for v in cells] == [8, 5, 8]
    assert editor.provider.await_args.args[2]["value"][0]["start_date"] == DAYS[1]
    assert editor.provider.await_args.args[2]["value"][0]["end_date"] == DAYS[1]


@pytest.mark.parametrize("defect", ["duplicate-mapping", "partial-api-pair", "sync-off", "invalid-booking-date"])
async def test_preflight_failure_leaves_all_dates_and_provider_untouched(editor, defect):
    if defect == "duplicate-mapping":
        editor.mappings.append(deepcopy(editor.mappings[0]))
    elif defect == "partial-api-pair":
        editor.mappings[0].pop("pms_api_rate_plan_code")
    elif defect == "sync-off":
        editor.mappings[0]["sync_availability"] = False
    elif defect == "invalid-booking-date":
        editor.bookings[0]["check_out"] = "2026-11-xx"
    original = deepcopy(editor.calendar)
    with pytest.raises(HTTPException) as exc:
        await apply(request())
    assert exc.value.status_code == 409
    assert exc.value.detail["provider_write_count"] == 0
    assert editor.calendar == original
    editor.save.assert_not_awaited()
    editor.provider.assert_not_awaited()


@pytest.mark.parametrize("net", [-1, 1000, True, 3.5, "3"])
def test_new_contract_rejects_non_integer_or_out_of_range_input(net):
    with pytest.raises(ValidationError):
        request(net)


async def test_legacy_base_endpoint_retains_its_contract(editor):
    payload = router.UnifiedBulkUpdateRequest(**request(5).model_dump())
    result = await router.unified_bulk_grid_update(payload, SimpleNamespace(tenant_id=TENANT, id="operator"), None)
    assert result["availability_input_mode"] == "base"
    assert [v["base_availability"] for v in await readback(editor)] == [5, 5, 5]


@pytest.mark.parametrize("collection", ["bookings", "room_night_locks"])
async def test_read_outage_is_fail_closed_before_any_mutation(editor, collection):
    getattr(editor.db, collection).find.side_effect = ConnectionError("synthetic storage outage")
    with pytest.raises(HTTPException) as exc:
        await apply(request(None if collection == "room_night_locks" else 3))
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "EXELY_REMAINING_INVENTORY_UNAVAILABLE"
    assert "synthetic storage" not in str(exc.value.detail)
    editor.save.assert_not_awaited()
    editor.provider.assert_not_awaited()


async def test_missing_property_mapping_is_rejected_before_any_mutation(editor):
    editor.connection.pop("hotel_code")
    with pytest.raises(HTTPException) as exc:
        await apply(request())
    assert exc.value.detail["error_code"] == "EXELY_PROPERTY_MAPPING_REQUIRED"
    editor.save.assert_not_awaited()
    editor.provider.assert_not_awaited()


@pytest.mark.parametrize("provider,agency_only", [("hotelrunner", False), ("agency", False), ("exely", True)])
async def test_new_endpoint_cannot_change_another_provider_mode(editor, monkeypatch, provider, agency_only):
    monkeypatch.setattr(router, "_detect_active_provider", AsyncMock(return_value={"provider": provider, "connection": editor.connection}))
    with pytest.raises(HTTPException) as exc:
        await apply(request(3, agencies_only=agency_only, agency_ids=["synthetic-agency"] if agency_only else None))
    assert exc.value.detail["error_code"] == "EXELY_REMAINING_MODE_REQUIRED"
    editor.save.assert_not_awaited()
    editor.provider.assert_not_awaited()


async def test_full_24_month_range_is_allowed_without_provider_or_calendar_access(monkeypatch):
    database = SimpleNamespace(exely_room_mappings=SimpleNamespace(find=MagicMock(return_value=cursor([
        {"exely_room_code": ROOM, "exely_rate_plan_code": RATE, "pms_room_type": "Standard"},
    ]))), room_night_locks=SimpleNamespace(find=MagicMock(return_value=cursor([]))))
    monkeypatch.setattr(remaining_availability, "get_room_counts", AsyncMock(return_value=({"Standard": {"total": 8}}, {"Standard": [f"r{i}" for i in range(8)]})))
    monkeypatch.setattr(remaining_availability, "get_active_bookings", AsyncMock(return_value=[]))
    values = await remaining_availability.prepare_exely_remaining_values(database, TENANT, [(ROOM, RATE)], {ROOM: 8}, "2026-11-02", "2028-11-01", None)
    assert len(values.base_values) == 731 and set(values.base_values.values()) == {8}
    with pytest.raises(HTTPException):
        await remaining_availability.prepare_exely_remaining_values(database, TENANT, [(ROOM, RATE)], {ROOM: 8}, "2026-11-02", "2028-11-02", None)


@pytest.mark.parametrize("stock_mode", ["manual", "automatic"])
async def test_existing_editor_full_two_room_period_reaches_one_quota_checked_soap(editor, monkeypatch, stock_mode):
    """Do not stop the editor test at a mocked delivery success (the old gap)."""
    editor.mappings.append({**editor.mappings[0], "pms_room_type": "Deluxe",
                            "exely_room_code": "panel-deluxe", "pms_api_room_code": "soap-deluxe"})
    rooms = [{"id": f"room-{i}", "room_type": "Standard", "status": "available"} for i in range(8)]
    rooms.extend({"id": f"deluxe-{i}", "room_type": "Deluxe", "status": "available"} for i in range(8))
    editor.db.rooms.find.side_effect = lambda query, projection: cursor(rooms)
    if stock_mode == "automatic":
        editor.bookings.clear()
    redis = SimpleNamespace(eval=AsyncMock(return_value=[1, 0, 0]))
    provider = ExelyProvider(
        username="synthetic", password="synthetic", hotel_code="synthetic-property",
        connection_id="editor-full-period",
        quota_guard=ExelyProviderQuota(TENANT, "synthetic-property", redis_client=redis),
    )
    provider._transport.send_soap = AsyncMock(return_value=b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/></OTA_HotelAvailNotifRS></s:Body></s:Envelope>')
    monkeypatch.setattr(ari_delivery, "ari_write_block_reason", lambda: "")
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.ari_write_block_reason", lambda: "")
    monkeypatch.setattr(ari_delivery, "_prepare_delivery", AsyncMock(return_value=(True, None)))
    monkeypatch.setattr(ari_delivery, "_mark_sending", AsyncMock(return_value=True))
    monkeypatch.setattr(ari_delivery, "_finish", AsyncMock(return_value=True))

    async def deliver(tenant, operation, payload):
        assert tenant == TENANT and operation == "availability_batch"
        return await deliver_exely_ari(tenant, operation, payload, provider=provider, write_enabled=True)

    editor.provider.side_effect = deliver
    result = await apply(request(start_date="2026-11-02", end_date="2028-11-01", per_room_values=[
        {"room_type_code": ROOM, "rate_plan_codes": [RATE], "availability": 6 if stock_mode == "manual" else None},
        {"room_type_code": "panel-deluxe", "rate_plan_codes": [RATE], "availability": 8 if stock_mode == "manual" else None},
    ]))
    assert result["saved"] == 1462
    assert result["provider_verified"] is True and result["provider_write_count"] == 1
    assert result["provider_delivery_state"] == "CONFIRMED"
    assert len(editor.calendar) == 1462
    editor.provider.assert_awaited_once()
    provider._transport.send_soap.assert_awaited_once()
    redis.eval.assert_awaited_once()
    quota_args = redis.eval.await_args.args
    key_count = quota_args[1]
    assert quota_args[2 + key_count:5 + key_count] == (731, 1460, 2)
    envelope = etree.fromstring(provider._transport.send_soap.await_args.args[0].encode())
    ns = {"ota": "http://www.opentravel.org/OTA/2003/05"}
    containers = envelope.findall(".//ota:AvailStatusMessages", ns)
    assert len(containers) == 1 and containers[0].get("HotelCode") == "synthetic-property"
    controls = envelope.findall(".//ota:StatusApplicationControl", ns)
    assert len(controls) == 2
    assert {c.get("InvTypeCode") for c in controls} == {"soap-standard", "soap-deluxe"}
    assert all(c.get("Start") == "2026-11-02" and c.get("End") == "2028-11-01"
               and c.get("RatePlanCode") == "soap-base" for c in controls)
    assert [v.get("BookingLimit") for v in envelope.findall(".//ota:AvailStatusMessage", ns)] == (["6", "8"] if stock_mode == "manual" else ["8", "8"])
    assert [row["rate"] for row in editor.calendar if row["date"] in DAYS and row["room_type_code"] == ROOM] == [100] * 3
