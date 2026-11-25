"""Current debt must agree across reports even when extras use the legacy ledger."""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from modules.pms_core.daily_reconciliation import build_daily_reconciliation
from routers.departments import reports as department_reports
from routers.finance import dashboards, mobile
from tests.test_finance_report_reconciliation import USER, seed_folios
from tests.test_finance_report_reconciliation import context as finance_context

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
context = finance_context


async def seed_extra(db):
    await seed_folios(db)
    await db.extra_charges.insert_one({"tenant_id": "A", "id": "extra", "booking_id": "bt", "folio_id": "try",
        "currency": "TRY", "amount": 120, "total": 120, "quantity": 1, "vat_amount": 20})


async def test_daily_current_receivables_match_mobile_with_owned_extra(ledger_db):
    await seed_extra(ledger_db)
    daily = await build_daily_reconciliation(ledger_db, "A", date(2026, 10, 2))
    pending = await mobile.get_pending_receivables_mobile.__wrapped__(current_user=USER)
    assert daily["ledger"]["ar_balance_by_currency"] == pending["totals_by_currency"] == {"EUR": 80, "TRY": 200}
    assert daily["ledger"]["ar_balance"] is None  # never add unlike currencies


async def test_finance_folio_detail_includes_extra_debt(ledger_db):
    await seed_extra(ledger_db)
    detail = await dashboards.get_folio_detail("try", current_user=USER)
    assert detail["outstanding_by_currency"] == {"TRY": 200}
    assert detail["outstanding"] == 200


@pytest.mark.parametrize("mirrored", [False, True])
async def test_company_positions_include_extra_once_and_keep_native_currency(ledger_db, monkeypatch, mirrored):
    await seed_extra(ledger_db)
    if mirrored:
        await ledger_db.folio_charges.insert_one({"tenant_id": "A", "id": "mirror", "folio_id": "try",
            "source_extra_charge_id": "extra", "currency": "TRY", "total": 120})
    monkeypatch.setattr(department_reports, "db", ledger_db)
    monkeypatch.setattr(department_reports, "_native_report_currency", AsyncMock(return_value="TRY"))
    rows = await ledger_db.folios.find({"tenant_id": "A", "company_id": "c"}).to_list(None)
    positions, failed, mixed = await department_reports._company_ledger_positions("A", rows)
    totals = {row["currency"]: row["balance"] for row in positions}
    assert totals == {"EUR": 80, "TRY": 200}
    assert failed == mixed == []
