"""Cross-page accounting contracts against isolated Mongo, never production."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import tenant_currency
from domains.accounting import gl_router
from routers.finance import accounting, folio
from shared_kernel import gl_posting

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator")


@pytest.fixture(autouse=True)
def context(monkeypatch, ledger_db):
    monkeypatch.setattr(accounting, "db", ledger_db)
    monkeypatch.setattr(folio, "db", ledger_db)
    monkeypatch.setattr(gl_router, "db", ledger_db)
    monkeypatch.setattr(folio, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-09-30"}))
    for module in (accounting, tenant_currency):
        monkeypatch.setattr(module, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    # Patch the canonical date provider, including code which imports it lazily.
    from core import business_date_service
    monkeypatch.setattr(business_date_service, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-09-30"}))


async def test_dashboard_month_dates_remaining_debt_and_bank_source(ledger_db):
    await ledger_db.accounting_invoices.insert_many([
        {"tenant_id": "A", "invoice_type": "sales", "issue_date": "2026-09-01", "status": "paid", "total": 100, "currency": "TRY"},
        {"tenant_id": "A", "issue_date": datetime(2026, 9, 30, 23, 59, tzinfo=UTC), "status": "partial", "total": 100, "amount_paid": 40, "due_date": "2026-09-29", "currency": "EUR"},
        {"tenant_id": "A", "issue_date": "2026-08-01", "status": "pending", "total": 50, "due_date": datetime(2026, 9, 1, tzinfo=UTC), "currency": "TRY"},
        {"tenant_id": "A", "issue_date": "2026-09-30", "status": "partial", "total": 20, "paid_amount": 5, "due_date": "2026-09-30", "currency": "USD"},
        *[{"tenant_id": "A", "issue_date": "2026-09-15", "status": status, "total": 9999, "currency": "TRY"} for status in ("cancelled", "canceled", "draft", "voided")],
        {"tenant_id": "A", "invoice_type": "purchase", "issue_date": "2026-09-15", "status": "pending", "total": 9999},
        {"tenant_id": "A", "invoice_type": "proforma", "issue_date": "2026-09-15", "status": "paid", "total": 9999},
        {"tenant_id": "B", "issue_date": "2026-09-15", "status": "paid", "total": 9999},
        {"tenant_id": "A", "issue_date": "2026-10-01", "status": "paid", "total": 9999},
    ])
    await ledger_db.expenses.insert_many([
        {"tenant_id": "A", "date": "2026-09-01", "total_amount": 10, "currency": "TRY"},
        {"tenant_id": "A", "date": datetime(2026, 9, 30, 23, 59, tzinfo=UTC), "amount": 2, "currency": "EUR"},
        {"tenant_id": "A", "date": "2026-09-15", "total_amount": 9999, "status": "cancelled"},
    ])
    await ledger_db.bank_accounts.insert_many([
        {"tenant_id": "A", "currency": " TL ", "current_balance": 20, "balance": 9999},
        {"tenant_id": "A", "currency": "EUR", "balance": 30},
        {"tenant_id": "B", "currency": "TRY", "current_balance": 9999},
    ])
    result = await accounting.get_accounting_dashboard.__wrapped__(current_user=USER, _perm=None)
    assert result["period"] == {"start": "2026-09-01", "end": "2026-09-30"}
    assert result["collected_income_by_currency"] == {"TRY": 100}
    assert result["accrued_revenue_by_currency"] == {"EUR": 100, "TRY": 100, "USD": 20}
    assert result["pending_amount_by_currency"] == {"EUR": 60, "TRY": 50, "USD": 15}
    assert result["overdue_amount_by_currency"] == {"EUR": 60, "TRY": 50}
    assert result["pending_invoices"] == 3
    assert result["overdue_invoices"] == 2
    assert result["monthly_expenses_by_currency"] == {"EUR": 2, "TRY": 10}
    assert result["bank_balance_by_currency"] == {"EUR": 30, "TRY": 20}


async def test_operational_balance_sheet_keeps_fx_inventory_and_partial_payables(ledger_db):
    await ledger_db.bank_accounts.insert_many([
        {"tenant_id": "A", "current_balance": 100, "balance": 999, "currency": "TRY"},
        {"tenant_id": "A", "balance": 10, "currency": "EUR"},
    ])
    await ledger_db.inventory_items.insert_many([
        {"tenant_id": "A", "quantity": 2, "unit_cost": 5, "currency": "EUR"},
        {"tenant_id": "A", "quantity": 3, "unit_cost": 4, "currency": "TRY"},
        {"tenant_id": "B", "quantity": 10, "unit_cost": 999},
    ])
    await ledger_db.accounting_invoices.insert_many([
        {"tenant_id": "A", "status": "partial", "total": 100, "paid_amount": 60, "currency": " EUR "},
        {"tenant_id": "A", "status": "overdue", "total": 20, "currency": "TRY"},
        {"tenant_id": "A", "status": "pending", "invoice_type": "purchase", "total": 999},
        {"tenant_id": "A", "status": "pending", "invoice_type": "proforma", "total": 999},
    ])
    await ledger_db.expenses.insert_many([
        {"tenant_id": "A", "payment_status": "partial", "total_amount": 50, "amount_paid": 20, "currency": "EUR"},
        {"tenant_id": "A", "payment_status": "pending", "amount": 5, "currency": "TRY"},
        {"tenant_id": "A", "payment_status": "paid", "total_amount": 999},
        {"tenant_id": "A", "payment_status": "pending", "status": "void", "total_amount": 999},
    ])
    result = await accounting.get_balance_sheet.__wrapped__(current_user=USER, _perm=None)
    assert result["assets"]["cash_by_currency"] == {"EUR": 10, "TRY": 100}
    assert result["assets"]["inventory_by_currency"] == {"EUR": 10, "TRY": 12}
    assert result["assets"]["receivables_by_currency"] == {"EUR": 40, "TRY": 20}
    assert result["assets"]["total_by_currency"] == {"EUR": 60, "TRY": 132}
    assert result["liabilities"]["total_by_currency"] == {"EUR": 30, "TRY": 5}
    assert result["equity"]["total_by_currency"] == {"EUR": 30, "TRY": 127}
    assert result["assets"]["total"] is None
    assert result["equity"]["total"] is None
    assert result["basis"] == "current_operational_positions_not_general_ledger"


async def test_profit_loss_and_vat_reconcile_legacy_expenses_and_cancelled_documents(ledger_db):
    await ledger_db.accounting_invoices.insert_many([
        {"tenant_id": "A", "issue_date": "2026-09-01", "status": "paid", "total": 120, "total_vat": 20, "currency": "EUR", "items": [{"description": "Room", "total": 100}]},
        {"tenant_id": "A", "issue_date": datetime(2026, 9, 30, 23, 59, tzinfo=UTC), "status": "paid", "total": 30, "total_vat": 5, "currency": "EUR"},
        *[{"tenant_id": "A", "issue_date": "2026-09-15", "status": status, "total_vat": 9999} for status in ("draft", "cancelled", "voided")],
    ])
    await ledger_db.expenses.insert_many([
        {"tenant_id": "A", "date": "2026-09-01", "amount": 10, "total_amount": None, "vat_amount": 2, "currency": "EUR", "category": "supplies"},
        {"tenant_id": "A", "date": "2026-09-30", "amount": 9999, "total_amount": 0, "currency": "EUR", "category": "supplies"},
        {"tenant_id": "A", "date": "2026-09-15", "total_amount": 9999, "vat_amount": 9999, "status": "cancelled"},
    ])
    pl = await accounting.get_profit_loss_report.__wrapped__("2026-09-01", "2026-09-30", current_user=USER, _perm=None)
    vat = await accounting.get_vat_report("2026-09-01", "2026-09-30", current_user=USER)
    assert pl["total_revenue_by_currency"] == {"EUR": 150}
    assert pl["total_expenses_by_currency"] == {"EUR": 10}
    assert pl["gross_profit_by_currency"] == {"EUR": 140}
    assert sum(bucket.get("EUR", 0) for bucket in pl["revenue_breakdown_by_currency"].values()) == 150
    assert pl["expense_breakdown_by_currency"] == {"supplies": {"EUR": 10}}
    assert vat["sales_vat_by_currency"] == {"EUR": 25}
    assert vat["purchase_vat_by_currency"] == {"EUR": 2}


async def test_unknown_bank_balance_is_not_reported_as_zero(ledger_db):
    await ledger_db.bank_accounts.insert_one({"tenant_id": "A", "currency": "EUR"})
    result = await accounting.get_balance_sheet.__wrapped__(current_user=USER, _perm=None)
    assert result["unknown_bank_balance_count"] == 1
    assert result["complete"] is False
    assert result["assets"]["total"] is None
    assert result["equity"]["total"] is None


async def test_folio_mobile_kpis_and_list_match_effective_ledger_not_cached_balance(ledger_db):
    now = datetime.now(UTC)
    recent = (now - timedelta(hours=2)).isoformat()
    await ledger_db.folios.insert_many([
        {"tenant_id": "A", "id": "eur", "status": "open", "currency": "EUR", "balance": 0},
        {"tenant_id": "A", "id": "try", "status": "open", "currency": "TRY", "balance": 999},
        {"tenant_id": "A", "id": "credit", "status": "open", "currency": "TRY", "balance": 999},
        {"tenant_id": "A", "id": "zero", "status": "open", "currency": "TRY", "balance": 999},
        {"tenant_id": "B", "id": "foreign-tenant", "status": "open", "balance": 999},
    ])
    await ledger_db.folio_charges.insert_many([
        {"tenant_id": "A", "folio_id": "eur", "amount": 100, "created_at": recent},
        {"tenant_id": "A", "folio_id": "try", "total": 40, "created_at": now - timedelta(hours=1)},
        {"tenant_id": "A", "folio_id": "try", "total": 999, "voided": True, "created_at": recent},
        {"tenant_id": "A", "folio_id": "try", "total": 0, "created_at": (now + timedelta(days=1)).isoformat()},
    ])
    await ledger_db.payments.insert_many([
        {"id": "p", "tenant_id": "A", "folio_id": "eur", "amount": 20, "idempotency_key": "same", "processed_at": recent},
        {"id": "retry", "tenant_id": "A", "folio_id": "eur", "amount": 20, "idempotency_key": "same", "processed_at": recent},
        {"id": "refund", "tenant_id": "A", "folio_id": "eur", "amount": 10, "payment_type": "refund", "processed_at": recent},
        {"id": "failed", "tenant_id": "A", "folio_id": "try", "amount": 999, "status": "failed", "processed_at": recent},
        {"id": "try", "tenant_id": "A", "folio_id": "try", "amount": 10, "processed_at": now - timedelta(hours=1)},
        {"id": "credit", "tenant_id": "A", "folio_id": "credit", "amount": 200, "processed_at": (now - timedelta(days=3)).isoformat()},
        {"id": "old", "tenant_id": "A", "folio_id": "try", "amount": 0, "processed_at": (now - timedelta(days=2)).isoformat(), "created_at": recent},
    ])
    result = await folio.get_folio_dashboard_stats.__wrapped__(current_user=USER, _perm=None)
    assert result["total_open_folios"] == 4  # Includes zero and credit folios.
    assert result["outstanding_by_currency"] == {"EUR": 90, "TRY": 30}
    assert result["total_outstanding_balance"] is None
    assert result["recent_charges_24h"] == 2
    assert result["recent_payments_24h"] == 3
    listing = await folio.list_folios("open", SimpleNamespace(limit=50, offset=0), USER)
    by_id = {row["id"]: row for row in listing["folios"]}
    assert by_id["eur"]["balance_by_currency"] == {"EUR": 90}
    assert by_id["eur"]["balance"] == 90
    assert by_id["try"]["balance"] == 30
    assert by_id["credit"]["balance"] == -200
    assert by_id["zero"]["balance"] == 0
    assert listing["total"] == 4


async def test_folio_summary_database_failure_is_not_a_zero_receivable(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(folio, "_company_receivable_rows", AsyncMock(side_effect=RuntimeError("Database unavailable")))
    with pytest.raises(HTTPException) as failure:
        await folio.get_folio_dashboard_stats.__wrapped__(current_user=USER, _perm=None)
    assert failure.value.status_code == 503


async def test_gl_journal_pages_export_and_balance_detail_use_the_same_posted_records(ledger_db):
    await ledger_db.gl_accounts.insert_many([
        {"tenant_id": "A", "code": "100", "name": "Cash", "type": "asset"},
        {"tenant_id": "A", "code": "600", "name": "Revenue", "type": "revenue"},
        {"tenant_id": "A", "code": "700", "name": "Expense", "type": "expense"},
    ])
    await ledger_db.gl_journal_entries.insert_many([
        {"tenant_id": "A", "id": "sale", "entry_no": "sale", "date": "2026-09-01", "status": "posted", "posting_sequence": 1,
         "lines": [{"account_code": "100", "debit": 100}, {"account_code": "600", "credit": 100}]},
        {"tenant_id": "A", "id": "expense", "entry_no": "expense", "date": "2026-09-30", "status": "posted", "posting_sequence": 2,
         "lines": [{"account_code": "700", "debit": 40}, {"account_code": "100", "credit": 40}]},
        *[{"tenant_id": tenant, "id": status, "entry_no": status, "date": "2026-09-30", "status": status,
           "lines": [{"account_code": "100", "debit": 9999}, {"account_code": "600", "credit": 9999}]} for tenant, status in [("A", "draft"), ("A", "void"), ("B", "posted")]],
    ])
    first = await gl_router.journal_report("2026-09-01", "2026-09-30", 1, 0, USER)
    last = await gl_router.journal_report("2026-09-01", "2026-09-30", 1, 1, USER)
    assert first["total"] == 2
    assert first["entries"][0]["id"] == "sale"
    assert first["has_more"] is True
    assert last["entries"][0]["id"] == "expense"
    assert last["has_more"] is False
    _, _, journal = await gl_router._export_rows("A", "journal", "2026-09-01", "2026-09-30", None)
    assert {row[0] for row in journal} == {"sale", "expense"}
    balance = await gl_posting.compute_balance_sheet(ledger_db, "A", as_of="2026-09-30")
    _, _, exported = await gl_router._export_rows("A", "balance_sheet", None, None, "2026-09-30")
    assert balance["current_earnings"]["amount"] == 60
    assets = sum(row[3] for row in exported if row[0] == "Varlık")
    right = sum(row[3] for row in exported if row[0] in {"Özkaynak", "Yükümlülük"})
    assert assets == right == 60


@pytest.mark.parametrize("start,end", [("not-a-date", "2026-09-30"), ("2026-10-01", "2026-09-30")])
async def test_journal_report_rejects_invalid_dates(start, end):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as failure:
        await gl_router.journal_report(start, end, 200, 0, USER)
    assert failure.value.status_code == 400


async def test_gl_financial_aggregates_never_silently_truncate_posted_entries(monkeypatch):
    limits = []
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def sort(self, *_args):
            return self

        async def to_list(self, limit):
            limits.append(limit)
            return self.rows

    class Collection:
        def __init__(self, rows):
            self.rows = rows

        def find(self, *_args):
            return Cursor(self.rows)

    database = SimpleNamespace(
        gl_journal_entries=Collection([{"lines": [{"account_code": "600", "credit": 1.01}]}]),
        gl_accounts=Collection([{"code": "600", "type": "revenue", "name": "Revenue"}]),
    )
    monkeypatch.setattr(gl_router, "db", database)
    trial = await gl_posting.compute_trial_balance(database, "A")
    income = await gl_posting.compute_income_statement(database, "A")
    _, _, exported = await gl_router._export_rows("A", "journal", None, None, None)
    assert trial["totals"]["credit_balance"] == income["totals"]["revenue"] == 1.01
    assert exported[0][7] == 1.01
    assert limits == [None] * 5
