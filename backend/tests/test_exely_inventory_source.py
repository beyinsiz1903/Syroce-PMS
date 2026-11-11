"""Provider-only stock must not diverge from the next booking-event projection."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.channel_manager import availability_auto_sync as auto
from domains.channel_manager import rate_manager_router as legacy
from domains.channel_manager.exely_inventory_source import assert_exely_inventory_source
from domains.channel_manager.providers.exely import ari_delivery, ari_publish, exely_router

real_delivery = ari_delivery.deliver_exely_ari

TENANT = "synthetic-inventory-hotel"
USER = SimpleNamespace(tenant_id=TENANT, id="synthetic-operator", name="Operator")
DAYS = ["2026-11-23", "2026-11-24", "2026-11-25"]
pytestmark = pytest.mark.exely_failure_stress


def matches(row, query):
    for key, value in query.items():
        actual = row.get(key)
        if isinstance(value, dict):
            for op, limit in value.items():
                if op == "$in" and actual not in limit:
                    return False
                if op == "$ne" and actual == limit:
                    return False
                if op == "$gte" and (actual is None or actual < limit):
                    return False
                if op == "$lte" and (actual is None or actual > limit):
                    return False
                if op == "$gt" and (actual is None or actual <= limit):
                    return False
                if op == "$lt" and (actual is None or actual >= limit):
                    return False
        elif actual != value:
            return False
    return True


class Collection:
    def __init__(self, rows):
        self.rows = rows
        self.bulk_write = AsyncMock(side_effect=self.save)

    def find(self, query, projection):
        assert query["tenant_id"] == TENANT
        return SimpleNamespace(to_list=AsyncMock(side_effect=lambda limit: deepcopy([r for r in self.rows if matches(r, query)][:limit])))

    async def find_one(self, query, projection):
        return next((deepcopy(row) for row in self.rows if matches(row, query)), None)

    async def save(self, ops, **kwargs):
        for op in ops:
            assert op._filter["tenant_id"] == TENANT
            row = next((r for r in self.rows if matches(r, op._filter)), None)
            if row is None:
                row = dict(op._filter)
                self.rows.append(row)
            row.update(op._doc["$set"])


@pytest.fixture
def inventory(monkeypatch):
    mappings = [{"tenant_id": TENANT, "pms_room_type": category, "exely_room_code": code,
                 "exely_rate_plan_code": "BASE", "pms_api_room_code": f"wire-{code}",
                 "pms_api_rate_plan_code": "wire-BASE", "sync_availability": True}
                for category, code in [("Standard", "STD"), ("Deluxe", "DLX")]]
    rooms = [{"tenant_id": TENANT, "id": f"{category}-{i}", "room_type": category, "status": "available"}
             for category in ["Standard", "Deluxe"] for i in range(8)]
    calendar = [{"tenant_id": TENANT, "room_type_code": code, "rate_plan_code": "BASE", "date": day,
                 "availability": 3, "availability_mode": "manual_remaining", "rate": 100, "min_stay": 2}
                for code in ["STD", "DLX"] for day in DAYS]
    database = SimpleNamespace(
        exely_connections=Collection([{"tenant_id": TENANT, "is_active": True, "hotel_code": "synthetic-property", "currency": "USD"}]),
        exely_room_mappings=Collection(mappings), rooms=Collection(rooms),
        bookings=Collection([]), room_night_locks=Collection([]), rate_calendar=Collection(calendar),
    )
    deliver = AsyncMock(return_value=ari_delivery.ExelyARIDeliveryResult(True, "confirmed", "", "SUCCESS", 1, "synthetic-operation"))
    enqueue = AsyncMock(return_value={"accepted": True, "queued_operation_count": 1})
    for module in [exely_router, legacy, auto]:
        monkeypatch.setattr(module, "db", database)
    monkeypatch.setattr(exely_router, "deliver_exely_ari", deliver)
    monkeypatch.setattr(exely_router, "enqueue_exely_ari_update", enqueue)
    monkeypatch.setattr(exely_router, "ari_write_block_reason", lambda: "")
    monkeypatch.setattr(exely_router, "log_sync", AsyncMock())
    monkeypatch.setattr(legacy, "enqueue_exely_ari_update", enqueue)
    monkeypatch.setattr(legacy, "get_tenant_currency", AsyncMock(return_value=("USD", {})))
    monkeypatch.setattr(ari_publish, "enqueue_exely_ari_update", enqueue)
    return SimpleNamespace(db=database, deliver=deliver, enqueue=enqueue, mappings=mappings, calendar=calendar)


def update(value=9, room="wire-DLX", **kwargs):
    return exely_router.ExelyARIUpdate(room_type_code=room, rate_plan_code="wire-BASE",
        start_date=DAYS[0], end_date=DAYS[1], availability=value, **kwargs)


async def bulk(rows):
    return await exely_router.bulk_push_ari(rows, USER, None, "synthetic-inventory-key")


@pytest.mark.parametrize("surface", ["single", "batch", "mixed"])
async def test_provider_only_nine_cannot_leave_pms_manual_three_behind(inventory, surface):
    saved = deepcopy(inventory.calendar)
    with pytest.raises(HTTPException) as exc:
        if surface == "single":
            await exely_router.push_ari(update(), USER, None)
        else:
            await bulk([update()] + ([update(None, rate_amount=120)] if surface == "mixed" else []))
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "EXELY_INVENTORY_SOURCE_MISMATCH"
    assert exc.value.detail["expected_availability"] == 3
    assert exc.value.detail["requested_availability"] == 9
    inventory.deliver.assert_not_awaited()
    inventory.enqueue.assert_not_awaited()
    inventory.db.rate_calendar.bulk_write.assert_not_awaited()
    assert inventory.calendar == saved


async def test_matching_resend_and_new_bookings_share_manual_owner_stock(inventory):
    for row in inventory.calendar:
        if row["room_type_code"] == "DLX":
            row["availability"] = 9
    assert (await bulk([update()]))["provider_verified"] is True
    assert inventory.deliver.await_args.args[2]["value"][0]["availability"] == 9
    original = deepcopy(inventory.calendar)
    booking = {"tenant_id": TENANT, "room_id": None, "room_type": "Deluxe", "status": "confirmed",
               "check_in": "2026-11-23T14:00:00", "check_out": "2026-11-25T12:00:00"}
    inventory.db.bookings.rows.append(booking)

    for step, expected in enumerate([8, 7, 8]):
        inventory.enqueue.reset_mock()
        result = await auto._push_to_exely(TENANT, "Deluxe", {day: 6 for day in DAYS})
        assert result == {"configured": True, "queued_operations": 2, "errors": []}
        calls = inventory.enqueue.await_args_list
        assert [(c.kwargs["start_date"], c.kwargs["end_date"], c.kwargs["availability"]) for c in calls] == [
            (DAYS[0], DAYS[1], expected), (DAYS[2], DAYS[2], 9)]
        assert all(c.kwargs["room_type_code"] == "wire-DLX" for c in calls)
        # Same projection is permitted for a diagnostic resend; stale 9 is rejected.
        assert (await bulk([update(expected)]))["provider_verified"] is True
        with pytest.raises(HTTPException):
            await bulk([update(9)])
        if step == 0:
            inventory.db.bookings.rows.append(deepcopy(booking))
        elif expected == 7:
            inventory.db.bookings.rows.pop()
    assert inventory.calendar == original
    assert all(row["availability"] == 3 for row in inventory.calendar if row["room_type_code"] == "STD")


@pytest.mark.parametrize("surface", ["single", "bulk"])
async def test_legacy_resend_never_replaces_gross_base_with_remaining_value(inventory, surface):
    for row in inventory.calendar:
        if row["room_type_code"] == "DLX":
            row["availability"] = 9
    inventory.db.bookings.rows.append({"tenant_id": TENANT, "room_type": "Deluxe", "status": "confirmed",
        "check_in": DAYS[0], "check_out": DAYS[2]})
    if surface == "single":
        await legacy.update_rates(legacy.BulkRateUpdateRequest(updates=[legacy.RateUpdateRequest(
            room_type_code="DLX", rate_plan_code="BASE", start_date=DAYS[0], end_date=DAYS[1], availability=8)]), USER, None)
    else:
        await legacy.bulk_grid_update(legacy.BulkGridUpdateRequest(
            room_type_codes=["DLX"], rate_plan_codes=["BASE"], start_date=DAYS[0], end_date=DAYS[1],
            update_fields=["availability"], availability=8), USER, None)
    assert inventory.enqueue.await_args.kwargs["availability"] == 8
    assert all(row["availability"] == 9 and row["availability_mode"] == "manual_remaining"
               for row in inventory.calendar if row["room_type_code"] == "DLX")


@pytest.mark.parametrize("surface", ["single", "bulk"])
async def test_legacy_mismatch_blocks_price_and_stock_before_any_write(inventory, surface):
    saved = deepcopy(inventory.calendar)
    with pytest.raises(HTTPException) as exc:
        if surface == "single":
            await legacy.update_rates(legacy.BulkRateUpdateRequest(updates=[legacy.RateUpdateRequest(
                room_type_code="DLX", rate_plan_code="BASE", start_date=DAYS[0], end_date=DAYS[1], availability=9, rate=120)]), USER, None)
        else:
            await legacy.bulk_grid_update(legacy.BulkGridUpdateRequest(
                room_type_codes=["DLX"], rate_plan_codes=["BASE"], start_date=DAYS[0], end_date=DAYS[1],
                update_fields=["availability", "rate"], availability=9, rate=120), USER, None)
    assert exc.value.detail["error_code"] == "EXELY_INVENTORY_SOURCE_MISMATCH"
    assert inventory.calendar == saved
    inventory.enqueue.assert_not_awaited()
    inventory.db.rate_calendar.bulk_write.assert_not_awaited()


async def test_legacy_selected_weekdays_do_not_validate_or_touch_unselected_inventory(inventory):
    inventory.calendar[3]["availability"] = 9  # Monday 23 Nov, outside the Tuesday-only resend.
    await legacy.bulk_grid_update(legacy.BulkGridUpdateRequest(
        room_type_codes=["DLX"], rate_plan_codes=["BASE"], start_date=DAYS[0], end_date=DAYS[2],
        update_fields=["availability"], availability=3, selected_days=[2]), USER, None)
    assert inventory.enqueue.await_args.kwargs["start_date"] == DAYS[1]
    assert inventory.enqueue.await_args.kwargs["end_date"] == DAYS[1]
    assert inventory.calendar[3]["availability"] == 9


async def test_price_only_direct_action_does_not_require_an_inventory_source(inventory, monkeypatch):
    monkeypatch.setattr(inventory.db.exely_room_mappings, "find", lambda *_: (_ for _ in ()).throw(AssertionError("unexpected inventory read")))
    result = await bulk([update(None, rate_amount=120)])
    assert result["queued"] == 1
    inventory.enqueue.assert_awaited_once()


@pytest.mark.parametrize("fault", ["missing", "duplicate", "disabled", "partial", "foreign"])
async def test_unverified_mapping_blocks_before_any_sibling_delivery(inventory, fault):
    owner = inventory.mappings[-1]
    if fault == "missing": inventory.mappings.pop()
    elif fault == "duplicate": inventory.mappings.append(deepcopy(owner))
    elif fault == "disabled": owner["sync_availability"] = False
    elif fault == "partial": owner["pms_api_rate_plan_code"] = ""
    elif fault == "foreign": owner["tenant_id"] = "other-hotel"
    with pytest.raises(HTTPException) as exc:
        await bulk([update(3), update(None, rate_amount=120)])
    assert exc.value.detail["error_code"] == "EXELY_INVENTORY_SOURCE_MAPPING_REQUIRED"
    inventory.deliver.assert_not_awaited()
    inventory.enqueue.assert_not_awaited()


async def test_unavailable_calendar_blocks_whole_request(inventory, monkeypatch):
    monkeypatch.setattr(inventory.db.rate_calendar, "find", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException) as exc:
        await bulk([update(3), update(None, rate_amount=120)])
    assert exc.value.status_code == 503
    inventory.enqueue.assert_not_awaited()
    inventory.deliver.assert_not_awaited()


async def test_zero_and_automatic_inventory_use_the_same_projection(inventory):
    for row in inventory.calendar:
        if row["room_type_code"] == "DLX": row["availability"] = 0
    assert (await bulk([update(0)]))["confirmed"] == 1
    for row in inventory.calendar:
        if row["room_type_code"] == "DLX":
            row.update(availability=None, availability_mode="automatic")
    inventory.db.room_night_locks.rows.append({"tenant_id": TENANT, "room_id": "Deluxe-0", "night_date": DAYS[0], "lock_type": "hold"})
    await assert_exely_inventory_source(inventory.db, TENANT, [update(7).model_dump() | {"end_date": DAYS[0]}])
    with pytest.raises(HTTPException):
        await assert_exely_inventory_source(inventory.db, TENANT, [update(8).model_dump()])


@pytest.mark.parametrize("operation", ["availability", "availability_batch"])
async def test_queued_snapshot_is_rechecked_before_claim_or_provider_write(inventory, monkeypatch, operation):
    monkeypatch.setattr(ari_delivery, "db", inventory.db)
    monkeypatch.setattr(ari_delivery, "ari_write_block_reason", lambda: "")
    claim = AsyncMock()
    monkeypatch.setattr(ari_delivery, "_prepare_delivery", claim)
    provider = AsyncMock()
    # Queued stock 3 becomes stale when a newly imported booking consumes one.
    inventory.db.bookings.rows.append({"tenant_id": TENANT, "room_type": "Deluxe", "status": "confirmed",
        "check_in": DAYS[0], "check_out": DAYS[2]})
    row = update(3).model_dump()
    payload = {"property_id": "synthetic-property", **row,
               "value": [row] if operation == "availability_batch" else 3}
    result = await real_delivery(TENANT, operation, payload, provider=provider, write_enabled=True)
    assert not result.success and result.error_code == "EXELY_INVENTORY_SOURCE_MISMATCH"
    assert result.provider_write_count == 0
    claim.assert_not_awaited()
    provider.push_ari_operation.assert_not_awaited()


async def test_current_snapshot_reaches_durable_delivery_without_rewriting_its_identity(inventory, monkeypatch):
    monkeypatch.setattr(ari_delivery, "db", inventory.db)
    monkeypatch.setattr(ari_delivery, "ari_write_block_reason", lambda: "")
    sent = AsyncMock(return_value=ari_delivery.ExelyARIDeliveryResult(True, "confirmed", "", "SUCCESS", 1, "stable-key"))
    monkeypatch.setattr(ari_delivery, "_deliver", sent)
    row = update(3).model_dump()
    payload = {"property_id": "synthetic-property", **row, "value": 3, "operation_identity": "stable-key"}
    expected_identity = ari_delivery.preview_exely_ari("availability", {**payload, "tenant_id": TENANT}).operation_identity
    result = await real_delivery(TENANT, "availability", payload, write_enabled=True)
    assert result.success
    assert sent.await_args.args[1]["value"] == 3
    assert sent.await_args.args[2] == expected_identity
