from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.integrations import operational_gl_bridge as bridge
from tests.test_operational_gl_bridge import _collection

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


def database(charges=(), payments=()):
    return SimpleNamespace(gl_operational_mappings=_collection(one={**bridge.DEFAULT_MAPPING, "enabled": True}),
        folio_charges=_collection(rows=list(charges)), payments=_collection(rows=list(payments)), night_audit_runs=_collection())


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["EUR", "USD", "UNKNOWN"])
async def test_foreign_revenue_is_not_nominally_added_to_try_even_with_an_ambiguous_receipt_rate(monkeypatch, code):
    db = database([{"total": 100, "tax_amount": 10, "currency": "TRY"},
                   {"total": 100, "tax_amount": 10, "currency": code, "exchange_rate": 0.02}])
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    with pytest.raises(bridge.OperationalGLBridgeError, match="Source-day TRY valuation"):
        await bridge.post_night_audit_daily_to_gl(db, "hotel", "2026-10-23", run_id="run")
    post.assert_not_awaited()
    db.night_audit_runs.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_source_currency_is_resolved_from_its_own_folio_before_guard(monkeypatch):
    db = database([{"total": 100, "folio_id": "eur-folio"}])
    db.folios = _collection(rows=[{"id": "eur-folio", "currency": "EUR"}])
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    with pytest.raises(bridge.OperationalGLBridgeError, match="EUR"):
        await bridge.post_night_audit_daily_to_gl(db, "hotel", "2026-10-23", run_id="run")
    assert db.folios.find.call_args.args[0]["tenant_id"] == "hotel"
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_legacy_currency_and_foreign_payment_fail_before_any_partial_batch_post(monkeypatch):
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    for code in (None, "EUR"):
        db = database(payments=[{"amount": 100, "currency": code, "method": "cash"}])
        with pytest.raises(bridge.OperationalGLBridgeError, match="Source-day TRY valuation"):
            await bridge.post_night_audit_daily_to_gl(db, "hotel", "2026-10-23", run_id="run")
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_internal_allocations_non_cash_and_pending_rows_never_become_bank_receipts(monkeypatch):
    db = database(charges=[{"total": 500, "category": "split_adjustment", "currency": "EUR"},
                            {"total": 500, "category": "opening_balance", "currency": "TRY"}], payments=[
        {"amount": 500, "currency": "TRY", "method": method} for method in
        ("city_ledger", "security_deposit_application", "complimentary", "discount", "correction", "direct_bill")
    ] + [{"amount": 500, "currency": "USD", "method": "card", "status": "pending"}])
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    assert await bridge.post_night_audit_daily_to_gl(db, "hotel", "2026-10-23", run_id="run") == {"status": "skipped", "reason": "no_activity"}
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_reverses_cash_and_duplicate_transaction_is_not_collected_twice(monkeypatch):
    refund = {"id": "refund", "amount": 20, "currency": "TRY", "method": "cash", "payment_type": "refund"}
    db = database(payments=[refund, dict(refund)])
    post = AsyncMock(return_value={"id": "journal"})
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    result = await bridge.post_night_audit_daily_to_gl(db, "hotel", "2026-10-23", run_id="run")
    assert result["payment_total"] == -20
    assert post.await_args.kwargs["lines"] == [
        {"account_code": "100", "credit": 20, "memo": "Günlük tahsilatlar"},
        {"account_code": "120", "debit": 20, "memo": "Günlük folio tahsilat kapaması"}]


@pytest.mark.asyncio
async def test_unknown_method_does_not_default_to_bank(monkeypatch):
    post = AsyncMock()
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    with pytest.raises(bridge.OperationalGLBridgeError, match="Unmapped collection method"):
        await bridge.post_night_audit_daily_to_gl(database(payments=[{"amount": 100, "currency": "TRY", "method": "gift_card"}]), "hotel", "2026-10-23", run_id="run")
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_mongo_daily_batch_uses_business_day_not_catchup_wall_clock(ledger_db, monkeypatch):
    db = ledger_db
    await db.gl_operational_mappings.insert_one({"tenant_id": "hotel", "enabled": True})
    await db.folio_charges.insert_many([
        {"tenant_id": "hotel", "business_date": "2026-10-23", "date": "2026-10-24T10:00:00Z", "total": 110, "tax_amount": 10, "currency": "TRY"},
        {"tenant_id": "hotel", "business_date": "2026-10-22", "date": "2026-10-23T10:00:00Z", "total": 999, "tax_amount": 0, "currency": "TRY"},
        {"tenant_id": "other", "business_date": "2026-10-23", "total": 999, "currency": "TRY"},
    ])
    await db.payments.insert_many([
        {"tenant_id": "hotel", "business_date": "2026-10-23", "processed_at": "2026-10-24T10:00:00Z", "amount": 90, "method": "cash", "currency": "TRY"},
        {"tenant_id": "hotel", "business_date": "2026-10-23", "processed_at": "2026-10-24T10:00:00Z", "amount": 20, "method": "cash", "currency": "TRY", "payment_type": "refund"},
        {"tenant_id": "hotel", "business_date": "2026-10-22", "processed_at": "2026-10-23T10:00:00Z", "amount": 999, "method": "card", "currency": "TRY"},
        {"tenant_id": "hotel", "business_date": "2026-10-23", "amount": 999, "method": "city_ledger", "currency": "TRY"},
    ])
    post = AsyncMock(return_value={"id": "journal"})
    monkeypatch.setattr(bridge, "post_journal_entry", post)
    result = await bridge.post_night_audit_daily_to_gl(db, "hotel", "2026-10-23", run_id="run")
    assert result["charge_total"] == 110 and result["payment_total"] == 70
    assert sum(line.get("debit", 0) for line in post.await_args.kwargs["lines"]) == 180
    assert sum(line.get("credit", 0) for line in post.await_args.kwargs["lines"]) == 180
