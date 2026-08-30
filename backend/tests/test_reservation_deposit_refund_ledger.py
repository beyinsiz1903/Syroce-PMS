import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

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
        folios=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "folio-a",
                    "tenant_id": "tenant-a",
                    "booking_id": "booking-a",
                    "status": "open",
                }
            ),
            insert_one=AsyncMock(),
        ),
    )


def _patch(monkeypatch, database):
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_log_activity", AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "_refresh_cached_folio_balance",
        AsyncMock(return_value=0.0),
    )
    emitted = MagicMock()
    monkeypatch.setattr(webhook_retry_service, "schedule_emit_reservation_updated", emitted)
    claim = AsyncMock(return_value={"status": "acquired", "lock_id": "lock-a"})
    release = AsyncMock()

    async def run_transaction(**kwargs):
        return await kwargs["callback"]("session-a")

    monkeypatch.setattr(reservation_detail, "claim_short_window_dedup", claim)
    monkeypatch.setattr(reservation_detail, "release_idempotency", release)
    monkeypatch.setattr(
        reservation_detail,
        "_run_reservation_financial_transaction",
        run_transaction,
    )
    return emitted, claim, release


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
    emitted, _claim, _release = _patch(monkeypatch, database)

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
    assert result["payment"]["folio_id"] == "folio-a"
    assert result["refund"]["folio_id"] == "folio-a"
    assert result["payment"]["deposit_id"] == "deposit-a"
    assert result["payment"]["reference"].startswith("deposit-refund:")
    assert result["payment"]["reference"] != "reference-a"
    assert result["refund"]["payment_id"] == result["payment"]["id"]
    database.payments.insert_one.assert_awaited_once_with(
        result["payment"],
        session="session-a",
    )
    database.deposits.update_one.assert_awaited_once_with(
        {
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
        },
        {"$set": {"status": "refunded", "refunded_amount": 25.0}},
        session="session-a",
    )
    database.bookings.update_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"$set": {"paid_amount": 75.0}},
        session="session-a",
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
        session="session-a",
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


@pytest.mark.asyncio
async def test_duplicate_refund_click_fails_before_financial_writes(monkeypatch):
    database = _database(
        deposit={
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
            "amount": 25.0,
            "status": "received",
        }
    )
    _emitted, claim, _release = _patch(monkeypatch, database)
    claim.return_value = {"status": "duplicate", "lock_id": None}

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

    assert exc.value.status_code == 409
    database.deposit_refunds.insert_one.assert_not_awaited()
    database.payments.insert_one.assert_not_awaited()
    database.deposits.update_one.assert_not_awaited()
    database.bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_duplicate_key_is_safe_conflict(monkeypatch):
    database = _database(
        deposit={
            "id": "deposit-a",
            "booking_id": "booking-a",
            "tenant_id": "tenant-a",
            "amount": 25.0,
            "status": "received",
        }
    )
    _emitted, _claim, release = _patch(monkeypatch, database)
    monkeypatch.setattr(
        reservation_detail,
        "_run_reservation_financial_transaction",
        AsyncMock(side_effect=DuplicateKeyError("duplicate")),
    )

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

    assert exc.value.status_code == 409
    release.assert_awaited_once_with(reservation_detail.db, lock_id="lock-a")
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
