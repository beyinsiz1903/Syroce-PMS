from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import tenant_currency
from routers.finance import accounting


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class _Collection:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.queries = []

    def find(self, query, *_args, **_kwargs):
        self.query = query
        self.queries.append(query)
        return _Cursor(self.rows)


class _AggregateCollection:
    def __init__(self, scalar_total=0, currency_totals=None):
        self.scalar_total = scalar_total
        self.currency_totals = currency_totals or {}

    def aggregate(self, pipeline):
        group_id = pipeline[-1].get("$group", {}).get("_id")
        if group_id is None:
            rows = [{"_id": None, "total": self.scalar_total}] if self.scalar_total else []
        else:
            rows = [{"_id": code, "total": amount} for code, amount in self.currency_totals.items()]
        return _Cursor(rows)


@pytest.fixture
def current_user(monkeypatch):
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", lambda _tenant_id: _async_value(("TRY", "₺")))
    return SimpleNamespace(tenant_id="tenant-a")


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_profit_loss_does_not_add_foreign_currency_invoices(monkeypatch, current_user):
    invoices = [
        {"total": 100.0, "currency": "TRY", "items": [{"description": "Room", "total": 100.0}]},
        {"total": 20.0, "currency": "EUR", "items": [{"description": "Room", "total": 20.0}]},
    ]
    expenses = [{"total_amount": 40.0, "currency": "TRY", "category": "supplies"}]
    accounting_invoices = _Collection(invoices)
    monkeypatch.setattr(
        accounting,
        "db",
        SimpleNamespace(accounting_invoices=accounting_invoices, expenses=_Collection(expenses)),
    )

    result = await accounting.get_profit_loss_report(
        start_date="2026-09-01",
        end_date="2026-09-30",
        current_user=current_user,
        _perm=None,
    )

    assert result["total_revenue_by_currency"] == {"EUR": 20.0, "TRY": 100.0}
    assert result["total_expenses_by_currency"] == {"TRY": 40.0}
    assert result["gross_profit_by_currency"] == {"EUR": 20.0, "TRY": 60.0}
    assert result["revenue_breakdown_by_currency"] == {"Room": {"EUR": 20.0, "TRY": 100.0}}
    assert result["mixed_currency"] is True
    assert result["total_revenue"] is None
    assert result["gross_profit"] is None
    assert accounting_invoices.query["invoice_type"] == {"$nin": ["proforma", "purchase"]}


@pytest.mark.asyncio
async def test_vat_report_keeps_sales_and_purchase_vat_currencies_separate(monkeypatch, current_user):
    invoices = [
        {"total_vat": 10.0, "currency": "TRY"},
        {"total_vat": 2.0, "currency": "EUR"},
    ]
    expenses = [{"vat_amount": 4.0, "currency": "TRY"}]
    monkeypatch.setattr(
        accounting,
        "db",
        SimpleNamespace(accounting_invoices=_Collection(invoices), expenses=_Collection(expenses)),
    )

    result = await accounting.get_vat_report(
        start_date="2026-09-01",
        end_date="2026-09-30",
        current_user=current_user,
    )

    assert result["sales_vat_by_currency"] == {"EUR": 2.0, "TRY": 10.0}
    assert result["purchase_vat_by_currency"] == {"TRY": 4.0}
    assert result["vat_payable_by_currency"] == {"EUR": 2.0, "TRY": 6.0}
    assert result["mixed_currency"] is True
    assert result["sales_vat"] is None
    assert result["vat_payable"] is None


@pytest.mark.asyncio
async def test_vat_report_excludes_proforma_and_purchase_invoice_vat(monkeypatch, current_user):
    invoices = _Collection([{"total_vat": 10.0, "currency": "TRY"}])
    monkeypatch.setattr(
        accounting,
        "db",
        SimpleNamespace(accounting_invoices=invoices, expenses=_Collection([])),
    )

    result = await accounting.get_vat_report(
        start_date="2026-09-01",
        end_date="2026-09-30",
        current_user=current_user,
    )

    assert result["sales_vat"] == 10.0
    assert invoices.query["invoice_type"] == {"$nin": ["proforma", "purchase"]}


@pytest.mark.asyncio
async def test_financial_reports_include_the_complete_final_day(monkeypatch, current_user):
    invoices = _Collection([])
    expenses = _Collection([])
    monkeypatch.setattr(
        accounting,
        "db",
        SimpleNamespace(accounting_invoices=invoices, expenses=expenses),
    )

    await accounting.get_profit_loss_report.__wrapped__(
        start_date="2026-09-01",
        end_date="2026-09-30",
        current_user=current_user,
        _perm=None,
    )
    await accounting.get_vat_report(
        start_date="2026-09-01",
        end_date="2026-09-30",
        current_user=current_user,
    )

    expected = {"$gte": "2026-09-01T00:00:00", "$lte": "2026-09-30T23:59:59.999999"}
    assert invoices.queries[0]["issue_date"] == expected
    assert invoices.queries[1]["issue_date"] == expected
    assert expenses.queries[0]["date"] == expected
    assert expenses.queries[1]["date"] == expected


@pytest.mark.asyncio
async def test_accounting_dashboard_excludes_proforma_and_purchase_documents(monkeypatch, current_user):
    invoices = _Collection([{"status": "paid", "total": 100.0, "currency": "TRY"}])
    monkeypatch.setattr(
        accounting,
        "db",
        SimpleNamespace(
            accounting_invoices=invoices,
            expenses=_Collection([]),
            bank_accounts=_Collection([]),
        ),
    )

    # This is a report-calculation contract.  Bypass the tenant dashboard cache
    # so another dashboard test cannot supply a stale, unrelated fixture result.
    result = await accounting.get_accounting_dashboard.__wrapped__(current_user=current_user, _perm=None)

    assert result["monthly_income"] == 100.0
    assert invoices.query["invoice_type"] == {"$nin": ["proforma", "purchase"]}


@pytest.mark.asyncio
async def test_balance_sheet_keeps_assets_and_equity_by_currency(monkeypatch, current_user):
    monkeypatch.setattr(
        accounting,
        "db",
        SimpleNamespace(
            bank_accounts=_AggregateCollection(100.0, {"TRY": 100.0}),
            inventory_items=_AggregateCollection(50.0),
            accounting_invoices=_AggregateCollection(20.0, {"EUR": 20.0}),
            expenses=_AggregateCollection(10.0),
        ),
    )

    result = await accounting.get_balance_sheet(current_user=current_user, _perm=None)

    assert result["assets"]["cash_by_currency"] == {"TRY": 100.0}
    assert result["assets"]["receivables_by_currency"] == {"EUR": 20.0}
    assert result["assets"]["total_by_currency"] == {"EUR": 20.0, "TRY": 150.0}
    assert result["liabilities"]["total_by_currency"] == {"TRY": 10.0}
    assert result["equity"]["total_by_currency"] == {"EUR": 20.0, "TRY": 140.0}


@pytest.mark.asyncio
async def test_accounting_dashboard_does_not_add_foreign_bank_balances(monkeypatch):
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
        accounting,
        "db",
        SimpleNamespace(
            accounting_invoices=Collection([]),
            expenses=Collection([]),
            bank_accounts=Collection([{"balance": 100, "currency": "TRY"}, {"balance": 10, "currency": "EUR"}]),
        ),
    )
    monkeypatch.setattr(accounting, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))

    # Exercise the underlying calculation; the decorated endpoint deliberately
    # caches one tenant's dashboard for production requests.
    result = await accounting.get_accounting_dashboard.__wrapped__(
        current_user=SimpleNamespace(tenant_id="tenant-a"), _perm=None
    )

    assert result["total_bank_balance"] == 100.0
    assert result["bank_balance_by_currency"] == {"TRY": 100.0, "EUR": 10.0}
