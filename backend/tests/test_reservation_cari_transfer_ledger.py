import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers import reservation_detail


def _patch_atomic_financial_helpers(monkeypatch, *, dedup_status="acquired"):
    claim = AsyncMock(
        return_value={
            "status": dedup_status,
            "lock_id": "lock-a" if dedup_status == "acquired" else None,
        }
    )
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
    return claim, release


@pytest.mark.asyncio
async def test_cari_transfer_posts_visible_folio_payment(monkeypatch):
    booking = {
        "id": "booking-a",
        "tenant_id": "tenant-a",
        "guest_id": "guest-a",
        "paid_amount": 100.0,
    }
    cari = {
        "id": "cari-a",
        "tenant_id": "tenant-a",
        "name": "Test Cari",
        "balance": 50.0,
        "current_balance": 75.0,
    }
    folio = {
        "id": "folio-a",
        "tenant_id": "tenant-a",
        "booking_id": "booking-a",
        "status": "open",
    }

    bookings = SimpleNamespace(
        find_one=AsyncMock(return_value=booking),
        update_one=AsyncMock(),
    )
    folios = SimpleNamespace(
        find_one=AsyncMock(return_value=folio),
        insert_one=AsyncMock(),
    )
    cari_accounts = SimpleNamespace(
        find_one=AsyncMock(return_value=cari),
        update_one=AsyncMock(),
    )
    cari_transactions = SimpleNamespace(insert_one=AsyncMock())
    payments = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            bookings=bookings,
            folios=folios,
            cari_accounts=cari_accounts,
            cari_transactions=cari_transactions,
            payments=payments,
        ),
    )
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    _patch_atomic_financial_helpers(monkeypatch)
    monkeypatch.setattr(reservation_detail, "_log_activity", AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "_reservation_outstanding_balance",
        AsyncMock(return_value=250.0),
    )
    refresh = AsyncMock(return_value=250.0)
    monkeypatch.setattr(reservation_detail, "_refresh_cached_folio_balance", refresh)

    result = await reservation_detail.transfer_to_cari(
        "booking-a",
        reservation_detail.CariTransfer(
            amount=250.0,
            cari_account_id="cari-a",
            description="Test transfer",
        ),
        current_user=SimpleNamespace(
            id="user-a",
            tenant_id="tenant-a",
            role="manager",
            name="Test Operator",
        ),
        _perm=None,
    )

    assert result["success"] is True
    assert result["payment"]["folio_id"] == "folio-a"
    assert result["payment"]["method"] == "city_ledger"
    assert result["payment"]["payment_type"] == "city_ledger_transfer"
    assert result["payment"]["amount"] == 250.0
    assert result["payment"]["reference"].startswith("cari-transfer:")
    assert result["payment"]["reference"] != "cari-a"
    assert result["payment"]["cari_account_id"] == "cari-a"
    payments.insert_one.assert_awaited_once_with(
        result["payment"],
        session="session-a",
    )
    cari_accounts.update_one.assert_awaited_once_with(
        {"id": "cari-a", "tenant_id": "tenant-a"},
        {"$set": {"balance": 325.0, "current_balance": 325.0}},
        session="session-a",
    )
    bookings.update_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"$set": {"paid_amount": 350.0}},
        session="session-a",
    )
    refresh.assert_awaited_once_with("tenant-a", "folio-a")


@pytest.mark.asyncio
async def test_cari_transfer_does_not_write_without_owned_account(monkeypatch):
    bookings = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a"}),
        update_one=AsyncMock(),
    )
    cari_accounts = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        update_one=AsyncMock(),
    )
    payments = SimpleNamespace(insert_one=AsyncMock())
    cari_transactions = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            bookings=bookings,
            cari_accounts=cari_accounts,
            payments=payments,
            cari_transactions=cari_transactions,
            city_ledger_accounts=SimpleNamespace(
                find_one=AsyncMock(return_value=None),
                update_one=AsyncMock()
            ),
            city_ledger_transactions=SimpleNamespace(insert_one=AsyncMock()),
        ),
    )
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(
        reservation_detail,
        "_reservation_outstanding_balance",
        AsyncMock(return_value=250.0),
    )

    with pytest.raises(Exception) as exc:
        await reservation_detail.transfer_to_cari(
            "booking-a",
            reservation_detail.CariTransfer(
                amount=250.0,
                cari_account_id="foreign-cari",
            ),
            current_user=SimpleNamespace(
                id="user-a",
                tenant_id="tenant-a",
                role="manager",
                name="Test Operator",
            ),
            _perm=None,
        )

    assert getattr(exc.value, "status_code", None) == 404
    payments.insert_one.assert_not_awaited()
    cari_transactions.insert_one.assert_not_awaited()
    bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("outstanding,amount", [(0.0, 1.0), (-1.0, 1.0), (10.0, 10.01)])
async def test_cari_transfer_rejects_absent_or_exceeded_balance_without_writes(
    monkeypatch,
    outstanding,
    amount,
):
    bookings = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a"}),
        update_one=AsyncMock(),
    )
    cari_accounts = SimpleNamespace(find_one=AsyncMock(), update_one=AsyncMock())
    payments = SimpleNamespace(insert_one=AsyncMock())
    cari_transactions = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            bookings=bookings,
            cari_accounts=cari_accounts,
            payments=payments,
            cari_transactions=cari_transactions,
            city_ledger_accounts=SimpleNamespace(
                find_one=AsyncMock(return_value=None),
                update_one=AsyncMock()
            ),
            city_ledger_transactions=SimpleNamespace(insert_one=AsyncMock()),
        ),
    )
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(
        reservation_detail,
        "_reservation_outstanding_balance",
        AsyncMock(return_value=outstanding),
    )

    with pytest.raises(Exception) as exc:
        await reservation_detail.transfer_to_cari(
            "booking-a",
            reservation_detail.CariTransfer(amount=amount, cari_account_id="cari-a"),
            current_user=SimpleNamespace(
                id="user-a",
                tenant_id="tenant-a",
                role="manager",
                name="Test Operator",
            ),
            _perm=None,
        )

    assert getattr(exc.value, "status_code", None) == 409
    cari_accounts.find_one.assert_not_awaited()
    payments.insert_one.assert_not_awaited()
    cari_transactions.insert_one.assert_not_awaited()
    bookings.update_one.assert_not_awaited()


def test_cari_balance_preserves_larger_legacy_value():
    assert reservation_detail._cari_balance({"balance": 0, "current_balance": 100}) == 100
    assert reservation_detail._cari_balance({"balance": 75, "current_balance": 50}) == 75
    assert reservation_detail._cari_balance({}) == 0


@pytest.mark.asyncio
async def test_cari_transfer_duplicate_click_fails_before_financial_writes(monkeypatch):
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "folio-a", "booking_id": "booking-a"}),
            insert_one=AsyncMock(),
        ),
        cari_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "cari-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        cari_transactions=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
        city_ledger_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value=None),
            update_one=AsyncMock(),
        ),
        city_ledger_transactions=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(
        reservation_detail,
        "_reservation_outstanding_balance",
        AsyncMock(return_value=100.0),
    )
    _patch_atomic_financial_helpers(monkeypatch, dedup_status="duplicate")

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.transfer_to_cari(
            "booking-a",
            reservation_detail.CariTransfer(amount=10.0, cari_account_id="cari-a"),
            current_user=SimpleNamespace(
                id="user-a",
                tenant_id="tenant-a",
                role="manager",
                name="Test Operator",
            ),
            _perm=None,
        )

    assert exc.value.status_code == 409
    database.cari_transactions.insert_one.assert_not_awaited()
    database.payments.insert_one.assert_not_awaited()
    database.bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_cari_transfer_duplicate_key_is_safe_conflict(monkeypatch):
    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "paid_amount": 0.0,
                }
            ),
            update_one=AsyncMock(),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "folio-a", "booking_id": "booking-a"}),
            insert_one=AsyncMock(),
        ),
        cari_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "cari-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        cari_transactions=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
        city_ledger_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value=None),
            update_one=AsyncMock(),
        ),
        city_ledger_transactions=SimpleNamespace(insert_one=AsyncMock()),
    )
    monkeypatch.setattr(reservation_detail, "db", database)
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(
        reservation_detail,
        "_reservation_outstanding_balance",
        AsyncMock(return_value=100.0),
    )
    _claim, release = _patch_atomic_financial_helpers(monkeypatch)
    monkeypatch.setattr(
        reservation_detail,
        "_run_reservation_financial_transaction",
        AsyncMock(side_effect=DuplicateKeyError("duplicate")),
    )

    with pytest.raises(HTTPException) as exc:
        await reservation_detail.transfer_to_cari(
            "booking-a",
            reservation_detail.CariTransfer(amount=10.0, cari_account_id="cari-a"),
            current_user=SimpleNamespace(
                id="user-a",
                tenant_id="tenant-a",
                role="manager",
                name="Test Operator",
            ),
            _perm=None,
        )

    assert exc.value.status_code == 409
    release.assert_awaited_once_with(reservation_detail.db, lock_id="lock-a")
