from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from routers.finance import accounting
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


@pytest.mark.asyncio
async def test_new_pending_expense_does_not_create_a_cash_movement(monkeypatch):
    class Expenses:
        def __init__(self):
            self.rows = []

        async def count_documents(self, _query):
            return len(self.rows)

        async def insert_one(self, row):
            self.rows.append(row)

    class CashFlowRows:
        def __init__(self):
            self.rows = []

        async def insert_one(self, row):
            self.rows.append(row)

    expenses = Expenses()
    cash_flow = CashFlowRows()
    monkeypatch.setattr(accounting, "db", SimpleNamespace(expenses=expenses, cash_flow=cash_flow))
    monkeypatch.setattr(accounting, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(accounting, "_invalidate_accounting_caches", lambda *_args: None)

    expense = await accounting.create_expense(
        ExpenseCreateRequest(
            category="supplies",
            description="Coffee",
            amount=100,
            vat_rate=20,
            date="2026-09-28",
        ),
        current_user=SimpleNamespace(tenant_id="tenant-a", name="Finance"),
        _perm=None,
    )

    assert expense.payment_status.value == "pending"
    assert len(expenses.rows) == 1
    assert cash_flow.rows == []


@pytest.mark.asyncio
async def test_new_pending_invoice_does_not_create_a_cash_movement(monkeypatch):
    class Invoices:
        def __init__(self):
            self.rows = []

        async def count_documents(self, _query):
            return len(self.rows)

        async def insert_one(self, row):
            self.rows.append(row)

    class CashFlowRows:
        def __init__(self):
            self.rows = []

        async def insert_one(self, row):
            self.rows.append(row)

    invoices = Invoices()
    cash_flow = CashFlowRows()
    monkeypatch.setattr(accounting, "db", SimpleNamespace(accounting_invoices=invoices, cash_flow=cash_flow))
    monkeypatch.setattr(accounting, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(accounting, "_invalidate_accounting_caches", lambda *_args: None)

    invoice = await accounting.create_accounting_invoice(
        AccountingInvoiceCreateRequest(
            invoice_type="sales",
            customer_name="Cash-flow test guest",
            due_date="2026-10-15",
        ),
        current_user=SimpleNamespace(tenant_id="tenant-a", name="Finance"),
        _perm=None,
    )

    assert invoice.status.value == "pending"
    assert len(invoices.rows) == 1
    assert cash_flow.rows == []


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


@pytest.mark.asyncio
async def test_cash_flow_reads_all_rows_before_calculating_totals(monkeypatch):
    class Cursor:
        def __init__(self):
            self.limits = []

        def sort(self, *_args):
            return self

        async def to_list(self, limit):
            self.limits.append(limit)
            return [{"transaction_type": "income", "amount": 10, "currency": "TRY"}]

    cursor = Cursor()
    queries = []

    def find(query, *_args, **_kwargs):
        queries.append(query)
        return cursor

    monkeypatch.setattr(accounting, "db", SimpleNamespace(cash_flow=SimpleNamespace(find=find)))
    monkeypatch.setattr(accounting, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))

    result = await accounting.get_cash_flow(
        start_date="2026-09-01",
        end_date="2026-09-30",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
    )

    assert cursor.limits == [None]
    assert result["total_income"] == 10.0
    assert queries == [{"tenant_id": "tenant-a", "date": {"$gte": "2026-09-01T00:00:00", "$lte": "2026-09-30T23:59:59.999999"}}]
