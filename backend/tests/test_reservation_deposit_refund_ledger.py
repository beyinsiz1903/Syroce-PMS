import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers import reservation_detail, webhook_retry_service


def _user():
    return SimpleNamespace(
        id="user-a",
        tenant_id="tenant-a",
        role="manager",
        name="Test Operator",
    )


def _database(*, deposit, booking=None):
    return SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value=booking
                or {
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "paid_amount": 100.0,
                }
            ),
            update_one=AsyncMock(),
        ),
        deposits=SimpleNamespace(
            find_one=AsyncMock(return_value=deposit),
            update_one=AsyncMock(),
        ),
        deposit_refunds=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
    )


def _patch(monkeypatch, database):
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_log_activity", AsyncMock())
    emitted = MagicMock()
    monkeypatch.setattr(webhook_retry_service, "schedule_emit_reservation_updated", emitted)
    return emitted


@pytest.mark.asyncio
async def test_full_deposit_refund_posts_negative_payment(monkeypatch):
    database = _database(
        deposit={
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
            "amount": 25.0,
            "reference": "reference-a",
            "status": "received",
        }
    )
    emitted = _patch(monkeypatch, database)

    result = await reservation_detail.refund_deposit(
        "booking-a",
        reservation_detail.DepositRefund(
            deposit_id="deposit-a",
            refund_amount=25.0,
            refund_method="cash",
            reason="Test refund",
        ),
        current_user=_user(),
        _perm=None,
    )

    assert result["success"] is True
    assert result["remaining_amount"] == 0
    assert result["payment"]["amount"] == -25.0
    assert result["payment"]["payment_type"] == "refund"
    assert result["payment"]["deposit_id"] == "deposit-a"
    database.payments.insert_one.assert_awaited_once()
    database.deposits.update_one.assert_awaited_once_with(
        {
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
        },
        {"$set": {"status": "refunded", "refunded_amount": 25.0}},
    )
    database.bookings.update_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"$set": {"paid_amount": 75.0}},
    )
    emitted.assert_called_once()


@pytest.mark.asyncio
async def test_partial_refund_accumulates_refunded_amount(monkeypatch):
    database = _database(
        deposit={
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
            "amount": 100.0,
            "refunded_amount": 30.0,
            "status": "partially_refunded",
        }
    )
    _patch(monkeypatch, database)

    result = await reservation_detail.refund_deposit(
        "booking-a",
        reservation_detail.DepositRefund(
            deposit_id="deposit-a",
            refund_amount=20.0,
            refund_method="card",
        ),
        current_user=_user(),
        _perm=None,
    )

    assert result["remaining_amount"] == 50.0
    database.deposits.update_one.assert_awaited_once_with(
        {
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
        },
        {"$set": {"status": "partially_refunded", "refunded_amount": 50.0}},
    )


@pytest.mark.asyncio
async def test_refund_above_remaining_balance_fails_without_writes(monkeypatch):
    database = _database(
        deposit={
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
            "amount": 100.0,
            "refunded_amount": 80.0,
            "status": "partially_refunded",
        }
    )
    _patch(monkeypatch, database)

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.refund_deposit(
            "booking-a",
            reservation_detail.DepositRefund(
                deposit_id="deposit-a",
                refund_amount=25.0,
                refund_method="cash",
            ),
            current_user=_user(),
            _perm=None,
        )

    assert exc.value.status_code == 400
    database.deposit_refunds.insert_one.assert_not_awaited()
    database.payments.insert_one.assert_not_awaited()
    database.deposits.update_one.assert_not_awaited()
    database.bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_fully_refunded_deposit_cannot_be_refunded_again(monkeypatch):
    database = _database(
        deposit={
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
            "amount": 100.0,
            "status": "refunded",
        }
    )
    _patch(monkeypatch, database)

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.refund_deposit(
            "booking-a",
            reservation_detail.DepositRefund(
                deposit_id="deposit-a",
                refund_amount=10.0,
                refund_method="cash",
            ),
            current_user=_user(),
            _perm=None,
        )

    assert exc.value.status_code == 400
    database.deposit_refunds.insert_one.assert_not_awaited()
    database.payments.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_deposit_refund_is_scoped_to_booking_and_tenant(monkeypatch):
    database = _database(deposit=None)
    _patch(monkeypatch, database)

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.refund_deposit(
            "booking-a",
            reservation_detail.DepositRefund(
                deposit_id="foreign-deposit",
                refund_amount=10.0,
                refund_method="cash",
            ),
            current_user=_user(),
            _perm=None,
        )

    assert exc.value.status_code == 404
    query = database.deposits.find_one.await_args.args[0]
    assert query == {
        "id": "foreign-deposit",
        "booking_id": "booking-a",
        "tenant_id": "tenant-a",
    }
    database.deposit_refunds.insert_one.assert_not_awaited()
    database.payments.insert_one.assert_not_awaited()
