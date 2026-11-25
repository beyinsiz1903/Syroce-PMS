"""Refundable deposit liability is separate from revenue and legacy advances."""
import pytest
from fastapi import HTTPException

from tests.test_daily_reconciliation_contract import context as daily_context
from tests.test_daily_reconciliation_contract import result

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
context = daily_context


async def test_refundable_deposits_report_only_unused_balances_in_native_currencies(ledger_db):
    await ledger_db.deposits.insert_one({"tenant_id": "A", "amount": 60, "currency": "EUR", "status": "received"})
    await ledger_db.security_funds.insert_many([
        {"tenant_id": "A", "id": "eur", "currency": "EUR", "status": "held", "received_minor": 10000,
         "applied_minor": 3000, "refunded_minor": 2000, "remaining_minor": 5000},
        {"tenant_id": "A", "id": "usd", "currency": "USD", "status": "held", "received_minor": 1000,
         "applied_minor": 0, "refunded_minor": 0, "remaining_minor": 1000},
        {"tenant_id": "A", "id": "closed", "currency": "EUR", "status": "closed", "received_minor": 5000,
         "applied_minor": 5000, "refunded_minor": 0, "remaining_minor": 0},
        {"tenant_id": "B", "id": "foreign", "currency": "TRY", "status": "held", "remaining_minor": 999999},
    ])
    data = await result()
    assert data["ledger"]["security_fund_balance_by_currency"] == {"EUR": 50, "USD": 10}
    assert data["ledger"]["security_fund_balance"] is None
    assert data["ledger"]["security_fund_count"] == 2
    assert data["ledger"]["deposit_balance_by_currency"] == {"EUR": 60}
    assert not data["payments"]["total_by_currency"]
    assert not data["revenue"]["total_by_currency"]


@pytest.mark.parametrize("changes", [{"remaining_minor": 999}, {"remaining_minor": -1},
    {"remaining_minor": True}, {"currency": None}, {"status": "closed"}])
async def test_invalid_refundable_liability_cannot_be_reported_as_zero(ledger_db, changes):
    await ledger_db.security_funds.insert_one({"tenant_id": "A", "id": "broken", "currency": "EUR", "status": "held",
        "received_minor": 1000, "applied_minor": 0, "refunded_minor": 0, "remaining_minor": 1000, **changes})
    with pytest.raises(HTTPException):
        await result()
