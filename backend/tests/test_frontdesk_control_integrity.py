from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms import operations_router as ops
from modules.pms_core.allotment_usage import available_rooms, contract_usage
from routers import pms_services as services

USER = SimpleNamespace(id="actor", email="qa@example.invalid", tenant_id="tenant-qa")
CONTRACT = {"id": "c1", "tour_operator": "QA Operator", "room_type": "Junior Suite", "allocated_rooms": 3,
            "start_date": "2026-11-10", "end_date": "2026-11-14", "rate": 100, "release_days": 0, "currency": "TRY"}


def booking(id_, start="2026-11-10", end="2026-11-12", currency="TRY", **extra):
    return {"id": id_, "check_in": start, "check_out": end, "currency": currency,
            "total_amount": 200, "status": "confirmed", "allotment_contract_id": "c1", **extra}


def test_allotment_counts_concurrent_rooms_not_sequential_bookings():
    rows = [booking("a"), booking("b", "2026-11-12", "2026-11-14"), booking("c", "2026-11-11", "2026-11-13")]
    result = contract_usage(CONTRACT, rows)
    assert result["used_rooms"] == 2
    assert result["bookings_count"] == 3
    assert available_rooms(CONTRACT, 2) == 1
    assert available_rooms({**CONTRACT, "released_rooms": 1}, 2) == 0


def test_allotment_never_combines_currencies_or_assumes_unknown():
    result = contract_usage(CONTRACT, [booking("a", currency="TRY"), booking("b", currency="USD"), booking("c", currency=None)])
    assert result["total_revenue"] is None
    assert result["total_revenue_by_currency"] == {"TRY": 200, "USD": 200}
    assert result["unknown_currency_bookings"] == 1


def test_allotment_normalizes_bson_dates_and_ignores_cancelled_unrelated_and_boundaries():
    result = contract_usage(CONTRACT, [booking("a", datetime(2026, 11, 10), datetime(2026, 11, 12)),
        booking("b", status="cancelled"), booking("c", allotment_contract_id="elsewhere"),
        booking("d", start="2026-11-09", end="2026-11-10"), booking("e", "2026-11-14", "2026-11-15")])
    assert result["used_rooms"] == result["bookings_count"] == 1


@pytest.mark.parametrize("changes", [{"allocated_rooms": -1}, {"allocated_rooms": 1.5}, {"allocated_rooms": True},
    {"release_days": -1}, {"release_days": 1.5}, {"tour_operator": " "}, {"room_type": ""},
    {"end_date": "2026-11-09"}, {"start_date": "bad"}, {"rate": -1}, {"rate": "NaN"}, {"rate": "1e999"}, {"currency": "bad-code"}])
def test_invalid_allotment_is_rejected(changes):
    with pytest.raises(HTTPException) as exc:
        services._validated_contract({**CONTRACT, **changes})
    assert exc.value.status_code == 400


def test_zero_release_days_is_valid():
    assert services._validated_contract(CONTRACT)["release_days"] == 0


@pytest.mark.asyncio
async def test_release_uses_current_usage_and_compare_and_set(monkeypatch):
    contracts = SimpleNamespace(find_one=AsyncMock(return_value=CONTRACT), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    monkeypatch.setattr(services, "db", SimpleNamespace(allotment_contracts=contracts))
    monkeypatch.setattr(services, "_allotment_usage", AsyncMock(return_value={"used_rooms": 2}))
    result = await services.release_allotment_rooms("c1", current_user=USER)
    assert result["released_rooms"] == 1 and result["channel_inventory_changed"] is False
    query, update = contracts.update_one.await_args.args
    assert query == {"id": "c1", "tenant_id": USER.tenant_id, "released_rooms": None}
    assert update["$set"]["released_by"] == USER.id
    contracts.find_one.return_value = {**CONTRACT, "released_rooms": 1}
    again = await services.release_allotment_rooms("c1", current_user=USER)
    assert again["released_rooms"] == 0
    assert contracts.update_one.await_count == 1


@pytest.mark.asyncio
async def test_release_conflict_or_cross_tenant_stops(monkeypatch):
    contracts = SimpleNamespace(find_one=AsyncMock(return_value=CONTRACT), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0)))
    monkeypatch.setattr(services, "db", SimpleNamespace(allotment_contracts=contracts))
    monkeypatch.setattr(services, "_allotment_usage", AsyncMock(return_value={"used_rooms": 2}))
    with pytest.raises(HTTPException) as exc:
        await services.release_allotment_rooms("c1", current_user=USER)
    assert exc.value.status_code == 409
    contracts.find_one.return_value = None
    with pytest.raises(HTTPException) as exc:
        await services.release_allotment_rooms("other", current_user=USER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_kvkk_create_and_complete_atomically_keep_actor_events(monkeypatch):
    source = {}
    async def insert(doc):
        source.update(deepcopy(doc))
    collection = SimpleNamespace(insert_one=AsyncMock(side_effect=insert), find_one=AsyncMock(side_effect=lambda query: deepcopy(source)),
                                 update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    monkeypatch.setattr(ops, "db", SimpleNamespace(kvkk_requests=collection))
    created = await ops.create_kvkk_request({"guest_name": " Synthetic QA ", "type": "access", "details": "No actual export"}, current_user=USER)
    assert source["guest_name"] == "Synthetic QA"
    assert source["audit_events"][0]["actor_id"] == USER.id
    assert created["id"] == source["_id"]
    await ops.update_kvkk_request(created["id"], {"status": "completed"}, current_user=USER)
    query, change = collection.update_one.await_args.args
    assert query["tenant_id"] == USER.tenant_id and query["status"] == "pending"
    assert change["$set"]["status"] == "completed"
    assert change["$push"]["audit_events"]["previous_status"] == "pending"
    assert change["$push"]["audit_events"]["user"] == USER.email
    source.update(change["$set"])
    again = await ops.update_kvkk_request(created["id"], {"status": "completed"}, current_user=USER)
    assert again["already_applied"] is True
    assert collection.update_one.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"created_by": "spoof"}, {"tenant_id": "other"}, {"status": "bad"}, {"status": []}, {"details": 123}, {}])
async def test_kvkk_rejects_arbitrary_mutation(monkeypatch, body):
    db = SimpleNamespace(kvkk_requests=SimpleNamespace(update_one=AsyncMock()))
    monkeypatch.setattr(ops, "db", db)
    with pytest.raises(HTTPException) as exc:
        await ops.update_kvkk_request("r1", body, current_user=USER)
    assert exc.value.status_code == 400
    db.kvkk_requests.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"guest_name": " "}, {"guest_name": "QA", "type": "invalid"}, {"guest_name": "QA", "type": []}, {"guest_name": "QA", "details": None}])
async def test_kvkk_invalid_create_has_no_write(monkeypatch, body):
    db = SimpleNamespace(kvkk_requests=SimpleNamespace(insert_one=AsyncMock()))
    monkeypatch.setattr(ops, "db", db)
    with pytest.raises(HTTPException) as exc:
        await ops.create_kvkk_request(body, current_user=USER)
    assert exc.value.status_code == 400
    db.kvkk_requests.insert_one.assert_not_awaited()
