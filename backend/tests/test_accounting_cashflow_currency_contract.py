import pytest
from pydantic import ValidationError

from routers.finance.accounting import (
    AccountingInvoiceCreateRequest,
    ExpenseCreateRequest,
    InventoryItemCreateRequest,
    _accounting_currency,
    _currency_totals,
    _invoice_currency_terms,
)


def test_currency_normalization_supports_tl_alias_and_rejects_unknown_codes():
    assert _accounting_currency("tl") == "TRY"
    assert _accounting_currency(" eur ") == "EUR"
    with pytest.raises(ValueError, match="Unsupported currency"):
        _accounting_currency("XYZ")


def test_expense_and_inventory_requests_preserve_selected_currency():
    expense = ExpenseCreateRequest(
        category="supplies",
        description="Coffee",
        amount=100,
        vat_rate=20,
        date="2026-09-28",
        currency="eur",
    )
    inventory = InventoryItemCreateRequest(
        name="Coffee",
        category="supplies",
        unit="kg",
        quantity=4,
        unit_cost=10,
        currency="usd",
    )

    assert expense.currency == "EUR"
    assert inventory.currency == "USD"


def test_request_currency_validation_rejects_unsupported_currency():
    with pytest.raises(ValidationError, match="Unsupported currency"):
        ExpenseCreateRequest(
            category="supplies",
            description="Coffee",
            amount=100,
            vat_rate=20,
            date="2026-09-28",
            currency="XYZ",
        )


def test_currency_totals_never_add_unrelated_nominal_amounts():
    records = [
        {"amount": 100, "currency": "TRY", "status": "paid"},
        {"amount": 50, "currency": "EUR", "status": "paid"},
        {"amount": 25, "currency": "TL", "status": "pending"},
        {"amount": 10, "status": "paid"},
    ]

    assert _currency_totals(records, "amount", "TRY") == {"TRY": 135.0, "EUR": 50.0}
    assert _currency_totals(records, "amount", "TRY", lambda row: row["status"] == "paid") == {
        "TRY": 110.0,
        "EUR": 50.0,
    }


def test_standard_invoice_request_preserves_selected_currency_and_rate():
    request = AccountingInvoiceCreateRequest(
        invoice_type="sales",
        customer_name="Foreign guest",
        due_date="2026-10-15",
        currency="eur",
        exchange_rate=48.25,
    )

    assert request.currency == "EUR"
    assert _invoice_currency_terms(request.currency, request.exchange_rate, "TRY") == ("EUR", 48.25)


def test_foreign_invoice_requires_an_explicit_positive_accounting_rate():
    with pytest.raises(ValueError, match="kaç TRY"):
        _invoice_currency_terms("EUR", None, "TRY")
    with pytest.raises(ValueError, match="sıfırdan büyük"):
        _invoice_currency_terms("EUR", 0, "TRY")
    assert _invoice_currency_terms("TRY", None, "TRY") == ("TRY", 1.0)
