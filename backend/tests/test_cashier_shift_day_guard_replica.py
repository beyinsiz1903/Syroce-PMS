"""Cash cannot cross the open PMS/shift day; real isolated Mongo only."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms import cashier_service as cs

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


async def seed(db, monkeypatch, day):
    monkeypatch.setattr(cs, "db", db)
    await db.tenant_settings.insert_one({"tenant_id": "hotel", "business_date": "2026-11-13"})
    await db.cashier_shifts.insert_one({"_id": "shift", "tenant_id": "hotel", "status": "open",
                                       "business_date": day, "transactions": [], "cash_in": 0, "cash_out": 0})


async def record():
    return await cs.record_cash_transaction(tenant_id="hotel", amount=20, method="cash",
        direction="in", description="Synthetic native cash regression", idempotency_key="payment:original", require_open_shift=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("day", ["2026-11-12", None])
async def test_old_or_missing_day_shift_blocks_cash_before_any_movement(ledger_db, monkeypatch, day):
    await seed(ledger_db, monkeypatch, day)
    with pytest.raises(HTTPException) as error:
        await cs.ensure_active_shift("hotel", "cash")
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await record()
    assert error.value.status_code == 409
    shift = await ledger_db.cashier_shifts.find_one({"_id": "shift"})
    assert shift["transactions"] == [] and shift["cash_in"] == 0
    assert shift["business_date"] == day


@pytest.mark.asyncio
async def test_matching_day_accepts_once_and_replays_after_day_roll(ledger_db, monkeypatch):
    await seed(ledger_db, monkeypatch, "2026-11-13")
    assert (await cs.ensure_active_shift("hotel", "cash"))["_id"] == "shift"
    first = await record()
    assert first["business_date"] == "2026-11-13"
    await ledger_db.tenant_settings.update_one({"tenant_id": "hotel"}, {"$set": {"business_date": "2026-11-14"}})
    replay = await record()
    assert replay["id"] == first["id"]
    shift = await ledger_db.cashier_shifts.find_one({"_id": "shift"})
    assert len(shift["transactions"]) == 1 and shift["cash_in"] == 20


@pytest.mark.asyncio
async def test_day_changes_between_lookup_and_write_cannot_accept_cash(ledger_db, monkeypatch):
    await seed(ledger_db, monkeypatch, "2026-11-13")
    original_get = cs.get_active_shift
    async def move_day(*args, **kwargs):
        before = await original_get(*args, **kwargs)
        await ledger_db.cashier_shifts.update_one({"_id": "shift"}, {"$set": {"business_date": "2026-11-14"}})
        return before
    monkeypatch.setattr(cs, "get_active_shift", move_day)
    with pytest.raises(HTTPException) as error:
        await record()
    assert error.value.status_code == 409
    shift = await ledger_db.cashier_shifts.find_one({"_id": "shift"})
    assert shift["transactions"] == [] and shift["cash_in"] == 0


@pytest.mark.asyncio
async def test_non_cash_preflight_does_not_require_drawer_day(monkeypatch):
    shift = {"_id": "shift", "business_date": "2026-11-12"}
    monkeypatch.setattr(cs, "get_active_shift", AsyncMock(return_value=shift))
    assert await cs.ensure_active_shift("hotel", "bank_transfer") == shift
