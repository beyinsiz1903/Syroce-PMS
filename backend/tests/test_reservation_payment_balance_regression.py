import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

import routers.finance.folio as finance_folio
import routers.reservation_detail as reservation_detail


def test_summary_does_not_double_count_posted_room_charge():
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 3500.0, "paid_amount": 3955.0},
        [
            {"charge_type": "room_charge", "total": 3920.0, "voided": False},
            {"charge_type": "tax", "total": 35.0, "voided": False},
        ],
        [{"amount": 3955.0, "voided": False}],
        [],
        [],
    )

    assert summary["total_charges"] == 3955.0
    assert summary["total_payments"] == 3955.0
    assert summary["balance"] == 0.0


def test_summary_keeps_unposted_room_total_before_night_audit():
    summary = reservation_detail._build_financial_summary(
        {"total_amount": 3500.0, "paid_amount": 500.0},
        [{"charge_type": "minibar", "total": 100.0, "voided": False}],
        [{"amount": 500.0, "voided": False}],
        [],
        [],
    )

    assert summary["balance"] == 3100.0


@pytest.mark.asyncio
async def test_payment_refreshes_tenant_scoped_checkout_balance(monkeypatch):
    calculate = AsyncMock(return_value=125.5)
    update = AsyncMock()
    monkeypatch.setattr("core.utils.calculate_folio_balance", calculate)
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(folios=SimpleNamespace(update_one=update)),
    )

    balance = await reservation_detail._refresh_cached_folio_balance("tenant-a", "folio-a")

    assert balance == 125.5
    calculate.assert_awaited_once_with("folio-a", "tenant-a")
    update.assert_awaited_once_with(
        {"id": "folio-a", "tenant_id": "tenant-a"},
        {"$set": {"balance": 125.5}},
    )


@pytest.mark.asyncio
async def test_payment_void_reverses_tenant_scoped_booking_paid_amount(monkeypatch):
    find_one = AsyncMock(return_value={"paid_amount": 300.0})
    update_one = AsyncMock()
    monkeypatch.setattr(
        finance_folio,
        "db",
        SimpleNamespace(
            bookings=SimpleNamespace(find_one=find_one, update_one=update_one),
        ),
    )

    adjustment = await finance_folio._decrement_booking_paid_amount(
        "tenant-a",
        "booking-a",
        125.0,
    )

    assert adjustment == 125.0
    find_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"_id": 0, "paid_amount": 1},
    )
    update_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"$inc": {"paid_amount": -125.0}},
    )
