from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


@pytest.mark.asyncio
async def test_city_ledger_candidates_are_tenant_scoped_and_exclude_linked_companies(user, monkeypatch):
    company_find = Mock(
        return_value=_Cursor(
            [
                {"id": "company-new", "name": "Yeni Acente", "contact_email": "new@example.com", "payment_terms": "45"},
                {"id": "company-linked", "name": "Bağlı Acente"},
                {"id": "company-name-match", "name": "Mevcut Cari"},
            ]
        )
    )
    companies = SimpleNamespace(find=company_find)
    accounts = SimpleNamespace(
        find=lambda query, projection: _Cursor(
            [
                {"source_company_id": "company-linked", "account_name": "Bağlı Acente"},
                {"account_name": "Mevcut Cari"},
            ]
        )
    )
    monkeypatch.setattr(cashiering, "db", SimpleNamespace(companies=companies, city_ledger_accounts=accounts))

    result = await cashiering.get_city_ledger_candidates(credentials=None)

    assert result == {
        "candidates": [
            {
                "source_company_id": "company-new",
                "account_name": "Yeni Acente",
                "company_name": "Yeni Acente",
                "contact_person": None,
                "email": "new@example.com",
                "phone": None,
                "tax_number": None,
                "billing_address": None,
                "payment_terms": "45",
                "status": None,
            }
        ],
        "total_count": 1,
    }
    assert company_find.call_args.args[0] == {"tenant_id": "tenant-a"}


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
async def test_room_allocated_payment_is_persisted_against_the_selected_booking(user, collections, monkeypatch):
    accounts, transactions, _ = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 10.0,
    }
    accounts.update_one.return_value = SimpleNamespace(modified_count=1)
    monkeypatch.setattr(
        cashiering,
        "_city_ledger_booking_items",
        AsyncMock(
            return_value=(
                [{"booking_id": "booking-101", "open_amount": 4.0}],
                {"room_open_total": 4.0},
            )
        ),
    )

    result = await cashiering.post_city_ledger_payment(
        account_id="account-1",
        amount=4.0,
        payment_method="bank_transfer",
        idempotency_key="room-payment-1",
        allocations=[cashiering.CityLedgerPaymentAllocation(booking_id="booking-101", amount=4.0)],
        credentials=None,
    )

    stored = transactions.insert_one.await_args.args[0]
    assert stored["allocations"] == [{"booking_id": "booking-101", "amount": 4.0}]
    assert stored["booking_id"] == "booking-101"
    assert result["allocations"] == [{"booking_id": "booking-101", "amount": 4.0}]


@pytest.mark.asyncio
async def test_room_allocated_payment_rejects_an_amount_above_that_rooms_open_balance(user, collections, monkeypatch):
    accounts, transactions, _ = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 10.0,
    }
    monkeypatch.setattr(
        cashiering,
        "_city_ledger_booking_items",
        AsyncMock(return_value=([{"booking_id": "booking-101", "open_amount": 3.99}], {})),
    )

    with pytest.raises(HTTPException) as exc:
        await cashiering.post_city_ledger_payment(
            account_id="account-1",
            amount=4.0,
            payment_method="bank_transfer",
            idempotency_key="room-payment-too-large",
            allocations=[cashiering.CityLedgerPaymentAllocation(booking_id="booking-101", amount=4.0)],
            credentials=None,
        )

    assert exc.value.status_code == 409
    assert transactions.insert_one.await_count == 0


@pytest.mark.asyncio
async def test_room_allocated_payment_requires_allocations_to_equal_the_payment_total(user, collections):
    accounts, transactions, _ = collections
    accounts.find_one.return_value = {
        "id": "account-1",
        "tenant_id": "tenant-a",
        "account_name": "Demo",
        "current_balance": 10.0,
    }

    with pytest.raises(HTTPException) as exc:
        await cashiering.post_city_ledger_payment(
            account_id="account-1",
            amount=4.0,
            payment_method="bank_transfer",
            idempotency_key="room-payment-mismatch",
            allocations=[cashiering.CityLedgerPaymentAllocation(booking_id="booking-101", amount=3.0)],
            credentials=None,
        )

    assert exc.value.status_code == 400
    assert transactions.insert_one.await_count == 0


@pytest.mark.asyncio
async def test_room_open_items_keep_legacy_unallocated_payments_separate(monkeypatch):
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        async def to_list(self, _limit):
            return self.rows

    class Collection:
        def __init__(self, rows):
            self.rows = rows

        def find(self, *_args, **_kwargs):
            return Cursor(self.rows)

    monkeypatch.setattr(
        cashiering,
        "db",
        SimpleNamespace(
            city_ledger_transactions=Collection(
                [
                    {"transaction_type": "charge", "booking_id": "booking-101", "amount": 100, "status": "completed"},
                    {"transaction_type": "charge", "booking_id": "booking-102", "amount": 50},
                    {"transaction_type": "payment", "amount": 40, "allocations": [{"booking_id": "booking-101", "amount": 40}]},
                    {"transaction_type": "payment", "amount": 10},
                    {"transaction_type": "adjustment", "amount": 5},
                ]
            ),
            bookings=Collection(
                [
                    {"id": "booking-101", "room_number": "101", "guest_name": "Ayşe"},
                    {"id": "booking-102", "room_number": "102", "guest_name": "Mehmet"},
                ]
            ),
        ),
    )

    items, summary = await cashiering._city_ledger_booking_items("tenant-a", "account-1")
    items_by_booking = {item["booking_id"]: item for item in items}

    assert items_by_booking["booking-101"]["open_amount"] == 60.0
    assert items_by_booking["booking-101"]["room_number"] == "101"
    assert items_by_booking["booking-102"]["open_amount"] == 50.0
    assert summary == {
        "room_open_total": 110.0,
        "allocated_payment_total": 40.0,
        "unallocated_payment_total": 10.0,
        "adjustment_total": 5.0,
    }


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
