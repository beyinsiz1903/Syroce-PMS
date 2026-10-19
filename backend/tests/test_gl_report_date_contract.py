"""GL report filters must never turn an invalid selection into an all-time report."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from domains.accounting import gl_router
from shared_kernel.gl_periods import GLPeriodError
from shared_kernel.gl_posting import compute_balance_sheet, compute_income_statement, compute_trial_balance

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator")


@pytest.mark.parametrize("day", ["", " ", "invalid", "2026-02-30", "2026-10-07oops"])
@pytest.mark.parametrize("kind", ["trial", "income", "balance", "journal"])
async def test_invalid_report_date_rejected_before_read(day, kind):
    database = MagicMock()
    with pytest.raises(GLPeriodError):
        if kind == "trial":
            await compute_trial_balance(database, "A", as_of=day)
        elif kind == "income":
            await compute_income_statement(database, "A", start=day, end="2026-10-07")
        elif kind == "balance":
            await compute_balance_sheet(database, "A", as_of=day)
        else:
            gl_router._posted_journal_query("A", day, "2026-10-07")
    database.gl_journal_entries.find.assert_not_called()


async def test_reversed_income_period_is_rejected_before_read():
    database = MagicMock()
    with pytest.raises(GLPeriodError, match="başlangıç"):
        await compute_income_statement(database, "A", start="2026-10-08", end="2026-10-07")
    database.gl_journal_entries.find.assert_not_called()


@pytest.mark.parametrize("kind", ["trial", "income", "balance", "journal", "export"])
async def test_report_route_returns_validation_error_not_a_full_history_or_server_error(kind, monkeypatch):
    monkeypatch.setattr(gl_router, "db", MagicMock())
    with pytest.raises(HTTPException) as caught:
        if kind == "trial":
            await gl_router.trial_balance(as_of="", current_user=USER)
        elif kind == "income":
            await gl_router.income_statement(start="", end="2026-10-07", current_user=USER)
        elif kind == "balance":
            await gl_router.balance_sheet(as_of="", current_user=USER)
        elif kind == "journal":
            await gl_router.journal_report(start="", end="2026-10-07", limit=200, offset=0, current_user=USER)
        else:
            await gl_router.export_gl_report(report="trial_balance", format="xlsx", start=None, end=None, as_of="", current_user=USER)
    assert caught.value.status_code == 400


async def test_gl_statements_reconcile_exact_minor_units_at_inclusive_day_boundary(ledger_db):
    await ledger_db.gl_accounts.insert_many(
        [
            {"tenant_id": "A", "code": "100", "name": "Kasa", "type": "asset"},
            {"tenant_id": "A", "code": "600", "name": "Gelir", "type": "revenue"},
        ]
    )

    def entry(day, amount, **extra):
        return {
            "tenant_id": "A",
            "status": "posted",
            "date": day,
            "lines": [
                {"account_code": "100", "debit_minor": amount, "credit_minor": 0, "debit": 9999},
                {"account_code": "600", "debit_minor": 0, "credit_minor": amount, "credit": 9999},
            ],
            **extra,
        }

    await ledger_db.gl_journal_entries.insert_many(
        [
            entry("2026-10-06", 10),
            entry("2026-10-07", 20),
            entry("2026-10-08", 999),
            entry("2026-10-07", 999, status="draft"),
            entry("2026-10-07", 999, tenant_id="B"),
        ]
    )
    trial = await compute_trial_balance(ledger_db, "A", as_of="2026-10-07")
    income = await compute_income_statement(ledger_db, "A", end="2026-10-07")
    balance = await compute_balance_sheet(ledger_db, "A", as_of="2026-10-07")
    assert trial["totals"]["debit_balance_minor"] == 30
    assert trial["totals"]["credit_balance_minor"] == 30
    assert income["totals"]["net_income_minor"] == 30
    assert balance["assets"][0]["amount_minor"] == 30
    assert balance["totals"]["assets"] == 0.3
    assert balance["totals"]["balanced"] is True
    assert (await compute_income_statement(ledger_db, "A", start="2026-10-07", end="2026-10-07"))["totals"]["net_income_minor"] == 20
