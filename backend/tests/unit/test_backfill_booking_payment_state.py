"""Backfill of reservation payment state: dry run by default, only stale fields, undoable."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import backfill_booking_payment_state as backfill


def _match(row, query):
    for key, cond in query.items():
        value = row
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(cond, dict):
            if "$in" in cond and value not in cond["$in"]:
                return False
            if "$nin" in cond and value in cond["$nin"]:
                return False
        elif value != cond:
            return False
    return True


class _Coll:
    def __init__(self, rows=()):
        self.rows = [copy.deepcopy(r) for r in rows]
        self.before_write = None

    def find(self, query, *_a, **_k):
        rows = [copy.deepcopy(r) for r in self.rows if _match(r, query)]

        class _Cur:
            async def to_list(self, _n):
                return rows

            def __aiter__(self):
                self._it = iter(rows)
                return self

            async def __anext__(self):
                try:
                    return next(self._it)
                except StopIteration:
                    raise StopAsyncIteration from None

        return _Cur()

    async def find_one(self, query, *_a, **_k):
        return next((copy.deepcopy(r) for r in self.rows if _match(r, query)), None)

    async def distinct(self, key, query=None):
        return list({r.get(key) for r in self.rows if _match(r, query or {})})

    async def update_one(self, query, update):
        if self.before_write:
            hook, self.before_write = self.before_write, None
            hook()
        for row in self.rows:
            if _match(row, query):
                row.update(copy.deepcopy(update.get("$set", {})))
                for key in update.get("$unset", {}):
                    row.pop(key, None)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def insert_one(self, doc):
        self.rows.append(doc)


@pytest.fixture
def world(monkeypatch):
    import core.tenant_db as tenant_db
    import routers.reservation_detail as detail

    database = SimpleNamespace(
        bookings=_Coll([
            # Paid in cash before #1320: stale balance / status, no collected_amount.
            {"id": "b1", "tenant_id": "t1", "confirmation_code": "MKT-1", "total_amount": 8000, "balance": 8000, "payment_status": "pending"},
            # Already correct: must not be written.
            {"id": "b2", "tenant_id": "t1", "total_amount": 5000, "balance": 0.0, "payment_status": "paid", "collected_amount": 5000.0},
            # Other hotel.
            {"id": "b3", "tenant_id": "t2", "total_amount": 1000, "balance": 1000, "payment_status": "pending"},
        ]),
        payments=_Coll([
            {"tenant_id": "t1", "booking_id": "b1", "amount": 8000, "method": "cash", "status": "paid"},
            {"tenant_id": "t1", "booking_id": "b2", "amount": 5000, "method": "card", "status": "paid"},
            {"tenant_id": "t2", "booking_id": "b3", "amount": 400, "method": "card", "status": "paid"},
            {"tenant_id": "t2", "booking_id": "b3", "amount": 600, "method": "card", "status": "failed"},
        ]),
        booking_payment_state_backfill_runs=_Coll(),
    )
    balances = world_balances = {"b1": 0, "b2": 0, "b3": 600}
    database.balances = world_balances
    monkeypatch.setattr(detail, "_reservation_outstanding_balance", AsyncMock(side_effect=lambda _t, b, **_kw: balances[b["id"]]))
    monkeypatch.setattr(tenant_db, "get_system_db", lambda: database)
    return database


def _booking(world, booking_id):
    return next(r for r in world.bookings.rows if r["id"] == booking_id)


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(world):
    assert await backfill.main(["--all-tenants"]) == 0
    assert _booking(world, "b1")["payment_status"] == "pending"
    assert world.booking_payment_state_backfill_runs.rows[0]["found"] == 2


@pytest.mark.asyncio
async def test_apply_needs_the_explicit_switch(world, monkeypatch):
    monkeypatch.delenv("ALLOW_PAYMENT_STATE_BACKFILL", raising=False)
    assert await backfill.main(["--all-tenants", "--apply"]) == 2
    assert _booking(world, "b1")["balance"] == 8000


@pytest.mark.asyncio
async def test_apply_fixes_only_stale_records_and_undo_restores(world, monkeypatch):
    monkeypatch.setenv("ALLOW_PAYMENT_STATE_BACKFILL", "true")
    assert await backfill.main(["--all-tenants", "--apply"]) == 0
    b1, b2, b3 = (_booking(world, i) for i in ("b1", "b2", "b3"))
    assert (b1["balance"], b1["payment_status"], b1["collected_amount"]) == (0.0, "paid", 8000.0)
    assert "payment_state_backfill" not in b2  # already right: untouched
    assert (b3["balance"], b3["payment_status"], b3["collected_amount"]) == (600.0, "partial", 400.0)  # failed card not counted

    run_id = b1["payment_state_backfill"]["run_id"]
    assert await backfill.main(["--all-tenants", "--undo", run_id]) == 0
    b1 = _booking(world, "b1")
    assert (b1["balance"], b1["payment_status"]) == (8000, "pending")
    assert "collected_amount" not in b1 and "payment_state_backfill" not in b1


@pytest.mark.asyncio
async def test_tenant_scope_is_respected(world, monkeypatch):
    monkeypatch.setenv("ALLOW_PAYMENT_STATE_BACKFILL", "true")
    assert await backfill.main(["--tenant-id", "t2", "--apply"]) == 0
    assert _booking(world, "b1")["payment_status"] == "pending"
    assert _booking(world, "b3")["payment_status"] == "partial"


def test_scope_is_mandatory():
    with pytest.raises(SystemExit):
        import asyncio

        asyncio.run(backfill.main([]))


@pytest.mark.asyncio
async def test_payment_after_the_plan_is_not_overwritten(world):
    """Plan made, then a 600 payment lands and its own refresh stores 0 / paid:
    apply re-derives from the live payments and leaves the record right."""
    plan = await backfill.plan_tenant(world, "t2")
    world.payments.rows.append({"tenant_id": "t2", "booking_id": "b3", "amount": 600, "method": "cash", "status": "paid"})
    world.balances["b3"] = 0
    _booking(world, "b3").update(balance=0.0, payment_status="paid", collected_amount=1000.0)
    result = await backfill.apply_plan(world, plan, "run-1")
    assert result == {"written": 0, "already_right": 1, "conflicts": []}
    b3 = _booking(world, "b3")
    assert (b3["balance"], b3["payment_status"], b3["collected_amount"]) == (0.0, "paid", 1000.0)


@pytest.mark.asyncio
async def test_change_between_read_and_write_is_skipped_as_conflict(world):
    plan = await backfill.plan_tenant(world, "t1")

    def payment_refresh_lands():
        _booking(world, "b1").update(balance=500.0, payment_status="partial", collected_amount=7500.0)

    world.bookings.before_write = payment_refresh_lands
    result = await backfill.apply_plan(world, plan, "run-2")
    assert result["written"] == 0 and result["conflicts"] == ["b1"]
    b1 = _booking(world, "b1")
    assert (b1["balance"], b1["payment_status"]) == (500.0, "partial") and "payment_state_backfill" not in b1


@pytest.mark.asyncio
async def test_undo_leaves_records_changed_after_the_run(world):
    plan = await backfill.plan_tenant(world, "t1")
    assert (await backfill.apply_plan(world, plan, "run-3"))["written"] == 1
    # A later refund: the payment path re-derives 3.000 / partial / 5.000 collected.
    _booking(world, "b1").update(balance=3000.0, payment_status="partial", collected_amount=5000.0)
    result = await backfill.undo_run(world, ["t1"], "run-3")
    assert result == {"restored": 0, "conflicts": ["b1"]}
    b1 = _booking(world, "b1")
    assert (b1["balance"], b1["payment_status"], b1["collected_amount"]) == (3000.0, "partial", 5000.0)
