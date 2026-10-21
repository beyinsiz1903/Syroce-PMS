"""Real local Mongo cash/GL acceptance; never moves money or calls a provider."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import mice_finance as finance
from tests.test_mice_commercial_workflows import event
from tests.test_mice_mongo_acceptance import USER, wired  # noqa: F401
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


@pytest.fixture
async def setup(wired, monkeypatch):  # noqa: F811
    monkeypatch.setattr(finance, "get_system_db", lambda: wired)
    monkeypatch.setattr(finance, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-21"}))
    await event(wired)
    await wired.cashier_shifts.insert_one({"_id": "shift", "tenant_id": "A", "status": "open", "cash_in": 0, "cash_out": 0, "transactions": []})
    await wired.gl_accounts.insert_many([{"tenant_id": "A", "code": c, "name": c, "active": True, "type": "asset"} for c in ("100", "102", "108", "120")])
    return wired


def body(**extra):
    return finance.SettlementIn(**{"request_id": "test-request-123", "amount": 100, "method": "cash", "reference": "CASH-1", "reason": "Synthetic collection receipt", **extra})


@pytest.mark.asyncio
async def test_real_gl_cash_and_partial_refunds_reconcile_once(setup, monkeypatch):
    db = setup
    first = await finance.record_settlement("event", body(), USER)
    assert (await finance.record_settlement("event", body(), USER))["replayed"]
    for number, amount in enumerate((30, 70)):
        refund = finance.SettlementIn(request_id=f"refund-request-{number}", kind="refund", amount=amount, method="cash", original_payment_id=first["payment"]["id"], reference=f"REF-{number}", reason="Synthetic refund receipt")
        await finance.record_settlement("event", refund, USER)
    summary = await finance.list_settlements("event", USER)
    assert summary["totals"] == {"collected": 100, "refunded": 100, "net_collected": 0, "quoted_total": 120, "outstanding": 120, "customer_credit": 0}
    assert await db.payments.count_documents({}) == 3
    assert await db.cash_flow.count_documents({}) == 3
    assert await db.gl_journal_entries.count_documents({}) == 3
    shift = await db.cashier_shifts.find_one({"_id": "shift"})
    assert shift["cash_in"] == shift["cash_out"] == 100
    assert len(shift["transactions"]) == 3 and not shift["mice_pending_ids"]
    assert all(e["total_debit_minor"] == e["total_credit_minor"] for e in await db.gl_journal_entries.find({}).to_list(None))
    assert not (await db.mice_events.find_one({"id": "event"})).get("finance_pending")
    from domains.pms import cashier_service
    monkeypatch.setattr(cashier_service, "db", db)
    await db.cashier_shifts.update_one({"_id": "shift"}, {"$set": {"business_date": "2026-10-21"}})
    assert await cashier_service.reconcile_open_shift_payments("A") == 0
    shift = await db.cashier_shifts.find_one({"_id": "shift"})
    assert shift["cash_in"] == shift["cash_out"] == 100 and len(shift["transactions"]) == 3
    excess = finance.SettlementIn(request_id="refund-excess-1", kind="refund", amount=.01, method="cash", original_payment_id=first["payment"]["id"], reference="REF-X", reason="Synthetic excess refund")
    with pytest.raises(HTTPException) as exc: await finance.record_settlement("event", excess, USER)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_parallel_collections_cannot_exceed_event_balance(setup):
    results = await asyncio.gather(finance.record_settlement("event", body(), USER), finance.record_settlement("event", body(request_id="other-request-123"), USER), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1
    assert await setup.payments.count_documents({}) == 1


@pytest.mark.asyncio
async def test_lost_gl_result_preserves_pending_and_same_request_recovers(setup, monkeypatch):
    actual_post = finance.post_journal_entry
    async def lost(*args, **kwargs):
        await actual_post(*args, **kwargs)
        raise TimeoutError("response lost after durable journal")
    monkeypatch.setattr(finance, "post_journal_entry", lost)
    with pytest.raises(TimeoutError): await finance.record_settlement("event", body(), USER)
    assert await setup.payments.count_documents({}) == 0
    assert (await finance.list_settlements("event", USER))["pending"]
    monkeypatch.setattr(finance, "post_journal_entry", actual_post)
    await finance.record_settlement("event", body(), USER)
    assert await setup.gl_journal_entries.count_documents({}) == 1
    assert await setup.payments.count_documents({}) == 1


@pytest.mark.asyncio
async def test_foreign_bank_account_and_permissions_fail_closed(setup):
    await setup.bank_accounts.insert_one({"id": "bank", "tenant_id": "B", "currency": "TRY", "balance": 0})
    with pytest.raises(HTTPException) as exc:
        await finance.record_settlement("event", finance.SettlementIn(request_id="bank-request-123", amount=20, method="bank_transfer", bank_account_id="bank", reference="BNK", reason="Synthetic bank receipt"), USER)
    assert exc.value.status_code == 422
    assert await setup.gl_journal_entries.count_documents({}) == 0


@pytest.mark.asyncio
async def test_fx_bank_and_folio_rows_use_same_currency_and_original_rate(setup):
    await setup.mice_events.update_one({"id": "event"}, {"$set": {"currency": "EUR", "reservation_id": "booking"}})
    await setup.bank_accounts.insert_one({"id": "bank", "tenant_id": "A", "currency": "EUR", "balance": 0})
    await setup.bookings.insert_one({"id": "booking", "tenant_id": "A", "currency": "EUR"})
    await setup.folios.insert_one({"id": "folio", "tenant_id": "A", "booking_id": "booking", "status": "open", "currency": "EUR", "balance": 120})
    request = finance.SettlementIn(request_id="bank-request-123", amount=100, method="bank_transfer", bank_account_id="bank", exchange_rate=40, reference="BNK", reason="Synthetic bank receipt")
    payment = (await finance.record_settlement("event", request, USER))["payment"]
    refund = finance.SettlementIn(request_id="bank-refund-123", kind="refund", amount=25, method="bank_transfer", bank_account_id="bank", original_payment_id=payment["id"], reference="REF", reason="Synthetic partial refund")
    await finance.record_settlement("event", refund, USER)
    assert (await setup.bank_accounts.find_one({"id": "bank"}))["balance"] == 75
    assert (await setup.folios.find_one({"id": "folio"}))["balance"] == 45
    assert await setup.payments.count_documents({"booking_id": "booking", "currency": "EUR", "gl_exchange_rate": 40}) == 2
    payments = await setup.payments.find({}).to_list(None)
    assert sum(p["reporting_amount"] for p in payments) == 3000
    assert all(p["reporting_currency"] == "TRY" for p in payments)


@pytest.mark.asyncio
async def test_partial_fx_refund_cannot_consume_the_final_rounding_cent(setup):
    await setup.mice_events.update_one({"id": "event"}, {"$set": {"currency": "EUR"}})
    payment = (await finance.record_settlement("event", body(amount=.02, exchange_rate=.5), USER))["payment"]
    refund = dict(kind="refund", method="cash", original_payment_id=payment["id"], reference="REF", reason="Synthetic rounding refund")
    with pytest.raises(HTTPException) as error:
        await finance.record_settlement("event", body(request_id="rounding-refund-1", amount=.01, **refund), USER)
    assert error.value.status_code == 422
    assert not (await setup.mice_events.find_one({"id": "event"})).get("finance_pending")
    await finance.record_settlement("event", body(request_id="rounding-refund-2", amount=.02, **refund), USER)
    assert (await finance.list_settlements("event", USER))["totals"]["net_collected"] == 0
