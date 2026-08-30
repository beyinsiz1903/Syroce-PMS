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


@pytest.mark.asyncio
async def test_deposit_is_linked_to_reservation_folio_and_refreshes_balance(monkeypatch):
    folio = {
        "id": "folio-a",
        "tenant_id": "tenant-a",
        "booking_id": "booking-a",
        "status": "open",
    }
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "guest_id": "guest-a",
                    "status": "confirmed",
                    "paid_amount": 250,
                }
            ),
            update_one=AsyncMock(),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value=folio),
            insert_one=AsyncMock(),
        ),
        deposits=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_log_activity", AsyncMock())
    refresh_balance = AsyncMock(return_value=750)
    monkeypatch.setattr(reservation_detail, "_refresh_cached_folio_balance", refresh_balance)

    from routers import webhook_retry_service

    monkeypatch.setattr(webhook_retry_service, "schedule_emit_reservation_updated", lambda *_args, **_kwargs: None)

    result = await reservation_detail.record_deposit(
        "booking-a",
        reservation_detail.DepositRecord(amount=500, method="cash"),
        current_user=SimpleNamespace(
            id="user-a",
            tenant_id="tenant-a",
            role="manager",
            name="Test Operator",
        ),
        _perm=None,
    )

    assert result["deposit"]["folio_id"] == "folio-a"
    inserted_deposit = database.deposits.insert_one.await_args.args[0]
    inserted_payment = database.payments.insert_one.await_args.args[0]
    assert inserted_deposit["folio_id"] == "folio-a"
    assert inserted_payment["folio_id"] == "folio-a"
    assert inserted_payment["payment_type"] == "deposit"
    database.bookings.update_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"$set": {"paid_amount": 750.0}},
    )
    refresh_balance.assert_awaited_once_with("tenant-a", "folio-a")


@pytest.mark.asyncio
async def test_deposit_refund_prefers_original_folio(monkeypatch):
    database = SimpleNamespace(
        folios=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "folio-closed",
                    "tenant_id": "tenant-a",
                    "booking_id": "booking-a",
                    "status": "closed",
                }
            ),
            insert_one=AsyncMock(),
        )
    )
    monkeypatch.setattr(reservation_detail, "db", database)

    folio = await reservation_detail._ensure_reservation_folio(
        "tenant-a",
        {"id": "booking-a", "guest_id": "guest-a"},
        preferred_folio_id="folio-closed",
    )

    assert folio["id"] == "folio-closed"
    database.folios.find_one.assert_awaited_once_with(
        {"tenant_id": "tenant-a", "id": "folio-closed"},
        {"_id": 0},
    )
    database.folios.insert_one.assert_not_awaited()
