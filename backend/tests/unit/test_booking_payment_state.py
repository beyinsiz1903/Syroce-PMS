"""Reservation balance and payment status are derived from its payments."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import booking_payment_state as state

CASH = {"amount": 8000, "method": "cash", "payment_type": "final"}


@pytest.mark.parametrize("payments,balance,expected", [
    ([], 8000, "pending"),
    ([{**CASH, "amount": 3000}], 5000, "partial"),
    ([CASH], 0, "paid"),
    ([{"amount": 8000, "method": "city_ledger", "payment_type": "city_ledger_transfer"}], 0, "transferred"),
    ([{**CASH, "voided": True}], 8000, "pending"),
    ([CASH, {"amount": -8000, "payment_type": "refund", "status": "refunded"}], 8000, "refunded"),
    ([{"amount": 500, "method": "discount"}], 7500, "pending"),
])
def test_payment_state(payments, balance, expected):
    assert state.payment_state(balance=balance, payments=payments) == expected


def test_collected_excludes_transfers_voids_discounts_and_nets_refunds():
    payments = [CASH, {"amount": 2000, "method": "city_ledger"}, {"amount": 100, "voided": True},
                {"amount": 300, "method": "discount"}, {"amount": 1000, "payment_type": "refund"}]
    assert state.collected_amount(payments) == 7000
    assert state.transferred_amount(payments) == 2000


@pytest.mark.asyncio
async def test_refresh_writes_balance_status_and_collected(monkeypatch):
    import importlib

    written = {}
    db = SimpleNamespace(
        bookings=SimpleNamespace(find_one=AsyncMock(return_value={"id": "b1", "tenant_id": "t1", "total_amount": 8000}),
                                 update_one=AsyncMock(side_effect=lambda q, u: written.update(u["$set"]))),
        payments=SimpleNamespace(find=lambda *a, **k: SimpleNamespace(to_list=AsyncMock(return_value=[CASH]))),
    )
    monkeypatch.setattr(importlib.import_module("routers.reservation_detail"), "_reservation_outstanding_balance", AsyncMock(return_value=0.0))
    result = await state.refresh_booking_payment_state(db, "t1", "b1")
    assert result == written == {"balance": 0.0, "payment_status": "paid", "collected_amount": 8000.0}


@pytest.mark.asyncio
async def test_refresh_never_raises():
    db = SimpleNamespace(bookings=SimpleNamespace(find_one=AsyncMock(side_effect=RuntimeError("down"))))
    assert await state.refresh_booking_payment_state(db, "t1", "b1") is None
