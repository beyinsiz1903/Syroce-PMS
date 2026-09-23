from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domains.pms import cashier_service


def _cursor(rows):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows)
    return cursor


@pytest.mark.asyncio
async def test_reconcile_recovers_unstamped_cash_payment_into_open_shift(monkeypatch):
    shift = {
        "_id": "shift-1",
        "tenant_id": "tenant-1",
        "status": "open",
        "business_date": "2026-09-22",
        "opened_at": "2026-09-22T20:00:00",
        "transactions": [],
    }
    payments = SimpleNamespace(
        find=MagicMock(
            return_value=_cursor(
                [
                    {
                        "id": "payment-1",
                        "tenant_id": "tenant-1",
                        "amount": 1250,
                        "method": "cash",
                        "status": "paid",
                        "processed_at": "2026-09-23T00:15:00+03:00",
                        "processed_by": "Resepsiyon",
                    }
                ]
            )
        ),
        update_one=AsyncMock(),
    )
    fake_db = SimpleNamespace(payments=payments, cashier_shifts=SimpleNamespace(update_one=AsyncMock()))
    monkeypatch.setattr(cashier_service, "db", fake_db)

    record = AsyncMock(return_value={"id": "txn-1"})
    with (
        patch.object(cashier_service, "get_active_shift", new=AsyncMock(return_value=shift)),
        patch.object(cashier_service, "record_cash_transaction", new=record),
    ):
        recovered = await cashier_service.reconcile_open_shift_payments("tenant-1")

    assert recovered == 1
    payments.update_one.assert_awaited_once_with(
        {"id": "payment-1", "tenant_id": "tenant-1"},
        {"$set": {"business_date": "2026-09-22"}},
    )
    assert record.await_args.kwargs["idempotency_key"] == "payment:payment-1"
    assert record.await_args.kwargs["direction"] == "in"
    assert record.await_args.kwargs["require_open_shift"] is True


@pytest.mark.asyncio
async def test_reconcile_does_not_duplicate_existing_shift_payment(monkeypatch):
    shift = {
        "_id": "shift-1",
        "tenant_id": "tenant-1",
        "status": "open",
        "business_date": "2026-09-22",
        "opened_at": "2026-09-22T20:00:00",
        "transactions": [{"idempotency_key": "payment:payment-1"}],
    }
    payments = SimpleNamespace(
        find=MagicMock(
            return_value=_cursor(
                [
                    {
                        "id": "payment-1",
                        "tenant_id": "tenant-1",
                        "business_date": "2026-09-22",
                        "amount": 1250,
                        "method": "cash",
                        "processed_at": "2026-09-22T21:00:00",
                    }
                ]
            )
        ),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(
        cashier_service,
        "db",
        SimpleNamespace(payments=payments, cashier_shifts=SimpleNamespace(update_one=AsyncMock())),
    )
    record = AsyncMock()

    with (
        patch.object(cashier_service, "get_active_shift", new=AsyncMock(return_value=shift)),
        patch.object(cashier_service, "record_cash_transaction", new=record),
    ):
        recovered = await cashier_service.reconcile_open_shift_payments("tenant-1")

    assert recovered == 0
    record.assert_not_awaited()
    payments.update_one.assert_not_awaited()
