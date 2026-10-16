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

    def find(self, query, *_a, **_k):
        rows = [copy.deepcopy(r) for r in self.rows if _match(r, query)]

        class _Cur:
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

    async def distinct(self, key):
        return list({r.get(key) for r in self.rows})

    async def update_one(self, query, update):
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
    balances = {"b1": 0, "b2": 0, "b3": 600}
    monkeypatch.setattr(detail, "_reservation_outstanding_balance", AsyncMock(side_effect=lambda _t, b: balances[b["id"]]))
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
