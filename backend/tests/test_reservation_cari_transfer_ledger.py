import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers import reservation_detail


@pytest.mark.asyncio
async def test_cari_transfer_posts_visible_folio_payment(monkeypatch):
    booking = {
        "id": "booking-a",
        "tenant_id": "tenant-a",
        "guest_id": "guest-a",
        "paid_amount": 100.0,
    }
    cari = {"id": "cari-a", "tenant_id": "tenant-a", "name": "Test Cari"}
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
    folios = SimpleNamespace(find_one=AsyncMock(return_value=folio))
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
    monkeypatch.setattr(reservation_detail, "_log_activity", AsyncMock())
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
    payments.insert_one.assert_awaited_once()
    cari_accounts.update_one.assert_awaited_once_with(
        {"id": "cari-a", "tenant_id": "tenant-a"},
        {"$inc": {"balance": 250.0, "current_balance": 250.0}},
    )
    bookings.update_one.assert_awaited_once_with(
        {"id": "booking-a", "tenant_id": "tenant-a"},
        {"$set": {"paid_amount": 350.0}},
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
        ),
    )
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)

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
