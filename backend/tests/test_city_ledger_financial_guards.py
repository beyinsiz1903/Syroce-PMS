from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.finance import cashiering


@pytest.fixture
def user(monkeypatch):
    current_user = SimpleNamespace(tenant_id="tenant-a", role="super_admin", name="Operator")
    monkeypatch.setattr(cashiering, "get_current_user", AsyncMock(return_value=current_user))
    monkeypatch.setattr(cashiering, "_enforce", lambda *_: None)
    return current_user


@pytest.fixture
def collections(monkeypatch):
    accounts = SimpleNamespace(
        find_one=AsyncMock(),
        insert_one=AsyncMock(),
        update_one=AsyncMock(),
    )
    transactions = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        insert_one=AsyncMock(),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
        delete_one=AsyncMock(),
    )
    bookings = SimpleNamespace(find_one=AsyncMock(return_value={"_id": "booking-1"}))
    monkeypatch.setattr(
        cashiering,
        "db",
        SimpleNamespace(
            bookings=bookings,
            city_ledger_accounts=accounts,
            city_ledger_transactions=transactions,
        ),
    )
    return accounts, transactions, bookings


@pytest.mark.asyncio
async def test_create_account_rejects_duplicate_name_case_insensitively(user, collections):
    accounts, _, _ = collections
    accounts.find_one.return_value = {"_id": "existing"}

    with pytest.raises(HTTPException) as exc:
        await cashiering.create_city_ledger_account(
            {"account_name": " Demo Account ", "company_name": "Demo Company"},
            credentials=None,
        )

    assert exc.value.status_code == 409
    accounts.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_payment_rejects_overpayment_without_writes(user, collections):
    accounts, transactions, _ = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 0.0,
    }

    with pytest.raises(HTTPException) as exc:
        await cashiering.post_city_ledger_payment(
            account_id="account-1",
            amount=1.0,
            payment_method="cash",
            idempotency_key="request-1",
            credentials=None,
        )

    assert exc.value.status_code == 409
    transactions.insert_one.assert_not_awaited()
    accounts.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_payment_updates_balance_once_and_replays_idempotently(user, collections):
    accounts, transactions, _ = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 10.0,
    }
    accounts.update_one.return_value = SimpleNamespace(modified_count=1)

    result = await cashiering.post_city_ledger_payment(
        account_id="account-1",
        amount=4.0,
        payment_method="bank_transfer",
        idempotency_key="request-1",
        credentials=None,
    )

    assert result["new_balance"] == 6.0
    assert result["replayed"] is False
    transactions.insert_one.assert_awaited_once()
    accounts.update_one.assert_awaited_once()

    stored = transactions.insert_one.await_args.args[0]
    transactions.find_one.return_value = {
        **stored,
        "status": "completed",
        "new_balance": 6.0,
    }
    replay = await cashiering.post_city_ledger_payment(
        account_id="account-1",
        amount=4.0,
        payment_method="bank_transfer",
        idempotency_key="request-1",
        credentials=None,
    )

    assert replay["replayed"] is True
    transactions.insert_one.assert_awaited_once()
    accounts.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_payment_fails_closed_when_balance_changes_concurrently(user, collections):
    accounts, transactions, _ = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 10.0,
    }
    accounts.update_one.return_value = SimpleNamespace(modified_count=0)

    with pytest.raises(HTTPException) as exc:
        await cashiering.post_city_ledger_payment(
            account_id="account-1",
            amount=4.0,
            payment_method="cash",
            idempotency_key="request-2",
            credentials=None,
        )

    assert exc.value.status_code == 409
    transactions.delete_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_payment_compensates_when_transaction_finalization_fails(user, collections):
    accounts, transactions, _ = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 10.0,
    }
    accounts.update_one.side_effect = [
        SimpleNamespace(modified_count=1),
        SimpleNamespace(modified_count=1),
    ]
    transactions.update_one.return_value = SimpleNamespace(modified_count=0)

    with pytest.raises(RuntimeError, match="finalization failed"):
        await cashiering.post_city_ledger_payment(
            account_id="account-1",
            amount=4.0,
            payment_method="cash",
            idempotency_key="request-3",
            credentials=None,
        )

    assert accounts.update_one.await_count == 2
    rollback = accounts.update_one.await_args_list[1]
    assert rollback.args[1] == {"$inc": {"current_balance": 4.0}}
    transactions.delete_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_bill_rejects_invalid_amount_before_writes(user, collections):
    accounts, transactions, bookings = collections

    with pytest.raises(HTTPException) as exc:
        await cashiering.post_to_city_ledger(
            booking_id="booking-1",
            account_id="account-1",
            amount=-1.0,
            description="Demo charge",
            idempotency_key="request-1",
            credentials=None,
        )

    assert exc.value.status_code == 400
    bookings.find_one.assert_not_awaited()
    accounts.find_one.assert_not_awaited()
    transactions.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_bill_is_tenant_scoped_and_idempotent(user, collections):
    accounts, transactions, bookings = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 10.0,
        "credit_limit": 100.0,
    }
    accounts.update_one.return_value = SimpleNamespace(modified_count=1)

    result = await cashiering.post_to_city_ledger(
        booking_id="booking-1",
        account_id="account-1",
        amount=4.0,
        description="Demo charge",
        idempotency_key="request-1",
        credentials=None,
    )

    assert result["new_balance"] == 14.0
    assert result["replayed"] is False
    bookings.find_one.assert_awaited_once_with(
        {"id": "booking-1", "tenant_id": "tenant-a"},
        {"_id": 1},
    )
    update_filter = accounts.update_one.await_args.args[0]
    assert update_filter["tenant_id"] == "tenant-a"
    stored = transactions.insert_one.await_args.args[0]
    assert stored["booking_id"] == "booking-1"

    transactions.find_one.return_value = {
        **stored,
        "status": "completed",
        "new_balance": 14.0,
    }
    replay = await cashiering.post_to_city_ledger(
        booking_id="booking-1",
        account_id="account-1",
        amount=4.0,
        description="Demo charge",
        idempotency_key="request-1",
        credentials=None,
    )

    assert replay["replayed"] is True
    transactions.insert_one.assert_awaited_once()
    accounts.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_bill_rolls_back_when_finalization_fails(user, collections):
    accounts, transactions, _ = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 10.0,
        "credit_limit": 100.0,
    }
    accounts.update_one.side_effect = [
        SimpleNamespace(modified_count=1),
        SimpleNamespace(modified_count=1),
    ]
    transactions.update_one.return_value = SimpleNamespace(modified_count=0)

    with pytest.raises(RuntimeError, match="finalization failed"):
        await cashiering.post_to_city_ledger(
            booking_id="booking-1",
            account_id="account-1",
            amount=4.0,
            description="Demo charge",
            idempotency_key="request-2",
            credentials=None,
        )

    assert accounts.update_one.await_count == 2
    rollback = accounts.update_one.await_args_list[1]
    assert rollback.args[0]["tenant_id"] == "tenant-a"
    assert rollback.args[1] == {"$inc": {"current_balance": -4.0}}
    transactions.delete_one.assert_awaited_once()
