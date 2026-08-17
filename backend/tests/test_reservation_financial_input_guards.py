import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers import pms_reservations, reservation_detail


@pytest.mark.parametrize(
    "model,payload",
    [
        (
            reservation_detail.ExtraChargeAdd,
            {"description": "Zero charge", "amount": 0, "quantity": 1},
        ),
        (
            pms_reservations.ExtraChargeCreate,
            {"charge_name": "Zero charge", "charge_amount": 0},
        ),
        (
            reservation_detail.DailyRateEntry,
            {"date": "2026-08-17", "rate": 0},
        ),
    ],
)
def test_zero_financial_values_are_rejected_by_contract(model, payload):
    with pytest.raises(ValidationError):
        model(**payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["checked_out", "cancelled", "no_show"])
async def test_terminal_booking_cannot_receive_deposit(monkeypatch, status):
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "status": status,
                }
            ),
            update_one=AsyncMock(),
        ),
        deposits=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.record_deposit(
            "booking-a",
            reservation_detail.DepositRecord(amount=1, method="cash"),
            current_user=SimpleNamespace(
                id="user-a",
                tenant_id="tenant-a",
                role="manager",
                name="Test Operator",
            ),
            _perm=None,
        )

    assert exc.value.status_code == 409
    database.deposits.insert_one.assert_not_awaited()
    database.payments.insert_one.assert_not_awaited()
    database.bookings.update_one.assert_not_awaited()
