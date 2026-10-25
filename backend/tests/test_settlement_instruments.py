"""Real local replica transactions for source-backed instruments; no PSP calls."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core import audit_chain
from core.booking_atomicity import with_resource_locks
from domains.pms import cashier_service
from modules.pms_core import settlement_instruments as s
from modules.pms_core.reporting_financials import effective_collection
from shared_kernel.gl_posting import post_journal_entry, verify_journal_entry_hash

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
ACTOR = SimpleNamespace(id="finance", name="Ayşe Yılmaz", role="admin")


@pytest.fixture
async def store(ledger_db, monkeypatch):
    db = ledger_db
    monkeypatch.setattr(audit_chain, "_system_db", lambda: db)
    monkeypatch.setattr(cashier_service, "db", db)
    await db.tenant_settings.insert_one({"tenant_id": "A", "business_date": "2026-10-24"})
    await db.bookings.insert_one({"tenant_id": "A", "id": "b", "status": "checked_in", "guest_id": "g", "currency": "TRY"})
    await db.folios.insert_one({"tenant_id": "A", "id": "f", "booking_id": "b", "status": "open", "currency": "TRY"})
    await db.folio_charges.insert_one({"tenant_id": "A", "id": "c", "folio_id": "f", "booking_id": "b", "total": 1000,
        "amount": 1000, "tax_amount": 0, "currency": "TRY", "business_date": "2026-10-24"})
    await db.gl_accounts.insert_many([{"tenant_id": "A", "code": code, "name": code, "type": kind, "active": True} for code, kind in
        [("102", "asset"), ("120", "asset"), ("136", "asset"), ("336", "liability"), ("646", "revenue"), ("656", "expense"), ("770", "expense")]])
    await db.gl_operational_mappings.insert_one({"tenant_id": "A", "enabled": True, "receivable_account_code": "120", "bank_account_code": "102"})
    await db.cashier_shifts.insert_one({"_id": "shift", "tenant_id": "A", "status": "open", "business_date": "2026-10-24", "transactions": [], "cash_in": 0, "cash_out": 0})
    await db.loyalty_members.insert_one({"tenant_id": "A", "guest_id": "g", "points_balance": 10000})
    return db


async def atomic(db, callback, booking="b"):
    await s.prepare(db, "A")
    return await with_resource_locks(client=db.client, db=db, tenant_id="A", locks_collection="reservation_financial_locks",
        resources=sorted({("booking", booking), ("booking", "billing-policy")}), callback=callback)


async def funded_issue(db, kind, *, code="TRY", amount=10000, base=10000):
    kwargs = {} if code == "TRY" else {"currency": code, "foreign_amount": amount / 100, "exchange_rate": base / amount}
    entry = await post_journal_entry(db, "A", date="2026-10-23", memo="Özgün harici fonlama belgesi",
        lines=[{"account_code": "102", "debit": base / 100}, {"account_code": "336", "credit": base / 100, **kwargs}],
        source="manual", idempotency_key=str(uuid4()))
    body = s.Issue(request_id=uuid4(), booking_id="b", kind=kind, currency=code, amount_minor=amount,
        account_code="336", funding_entry_id=entry["id"], reference=str(uuid4()), reason="Kaynak fonlamanın kaydı")
    result = await atomic(db, lambda session: s.issue(db, "A", ACTOR, body, session=session))
    return result, body, entry


async def issued(db, kind, **changes):
    body = s.Issue(**{"request_id": uuid4(), "booking_id": "b", "kind": kind, "currency": "TRY", "amount_minor": 10000,
        "account_code": "102" if kind == "cheque_pending_clearance" else "136" if kind == "barter" else "770",
        "reference": str(uuid4()), "reason": "Belgeye dayalı yetkili limit", **({"point_value_minor": 10} if kind == "loyalty_redemption" else {}),
        **({"due_on": "2026-10-24"} if kind == "cheque_pending_clearance" else {}), **changes})
    return await atomic(db, lambda session: s.issue(db, "A", ACTOR, body, session=session)), body


def application(**changes):
    return s.Apply(**{"request_id": uuid4(), "booking_id": "b", "folio_id": "f", "amount_minor": 10000,
        "rate_to_try": "1", "rate_reference": "TRY sabit değer", "reference": str(uuid4()), "reason": "Belgeye bağlı mahsup", **changes})


async def apply(db, item, body):
    return await atomic(db, lambda session: s.apply(db, "A", ACTOR, item["id"], body, session=session, record_cash=cashier_service.record_cash_transaction))


async def reverse(db, op, body):
    return await atomic(db, lambda session: s.reverse(db, "A", ACTOR, op["id"], body, session=session, record_cash=cashier_service.record_cash_transaction))


@pytest.mark.parametrize("kind", list(s.KINDS))
async def test_all_six_methods_commit_and_reverse_with_real_gl_folio_audit_and_points(store, kind):
    db = store
    if kind in s.FUNDED:
        item, issue, funding = await funded_issue(db, kind)
    else:
        item, issue = await issued(db, kind)
    assert await db.payments.count_documents({}) == 0  # including pending cheques
    body = application()
    result = await apply(db, item, body)
    assert await apply(db, item, body) == result
    assert await atomic(db, lambda session: s.issue(db, "A", ACTOR, issue, session=session)) == item
    assert (await db.folios.find_one({"id": "f"}))["balance"] == 900
    payment = await db.payments.find_one({"id": result["payment_id"]})
    assert effective_collection(payment) == (100 if kind == "cheque_pending_clearance" else 0)
    assert (await s.reconcile(db, "A"))["healthy"]
    if kind == "cheque_pending_clearance":
        assert await s.exclude_direct_cheques(db, "A", [payment]) == []
    back = s.Reverse(request_id=uuid4(), booking_id="b", reference="İade dekontu 001", reason="Özgün mahsup iptali")
    undone = await reverse(db, result, back)
    assert await reverse(db, result, back) == undone
    with pytest.raises(HTTPException):
        await reverse(db, result, back.model_copy(update={"request_id": uuid4()}))
    assert (await db.folios.find_one({"id": "f"}))["balance"] == 1000
    fresh = await db.billing_instruments.find_one({"id": item["id"]})
    assert fresh["remaining_minor"] == fresh["issued_minor"] == 10000
    assert (await db.loyalty_members.find_one({"guest_id": "g"}))["points_balance"] == 10000
    assert all(verify_journal_entry_hash(row) for row in await db.gl_journal_entries.find({}).to_list(None))
    assert (await audit_chain.verify_chain("A"))["ok"]
    assert (await s.reconcile(db, "A"))["totals_by_currency"]["TRY"] == {"non_cash_minor": 0, "cleared_cheque_minor": 0}
    assert await db.payments.count_documents({}) == 2
    from routers.reservation_detail import _build_financial_summary
    summary = _build_financial_summary({"currency": "TRY", "total_amount": 1000},
        await db.folio_charges.find({}).to_list(None), await db.payments.find({}).to_list(None), [], [])
    assert summary["total_payments"] == 0 and summary["instrument_settlement_total"] == 0
    shift = await db.cashier_shifts.find_one({"_id": "shift"})
    assert len(shift["transactions"]) == (2 if kind == "cheque_pending_clearance" else 0)
    assert shift["cash_in"] == shift["cash_out"] == 0
    if kind == "cheque_pending_clearance":
        assert await s.exclude_direct_cheques(db, "A", await db.payments.find({}).to_list(None)) == []


@pytest.mark.parametrize("code", ["USD", "EUR", "GBP", "CHF"])
@pytest.mark.parametrize("rate,account", [("49", "646"), ("51", "656")])
async def test_foreign_wallet_preserves_carrying_value_and_books_explicit_realised_fx(store, code, rate, account):
    db = store
    await db.folios.update_one({"id": "f"}, {"$set": {"currency": code}})
    await db.bookings.update_one({"id": "b"}, {"$set": {"currency": code}})
    await db.folio_charges.update_one({"id": "c"}, {"$set": {"currency": code}})
    item, _, funding = await funded_issue(db, "wallet", code=code, base=500000)
    old = deepcopy(funding)
    body = application(rate_to_try=rate, fx_gain_account="646", fx_loss_account="656")
    result = await apply(db, item, body)
    journal = await db.gl_journal_entries.find_one({"id": result["gl_journal_entry_id"]})
    assert sum(row["debit_minor"] for row in journal["lines"]) == sum(row["credit_minor"] for row in journal["lines"])
    fx = next(row for row in journal["lines"] if row["account_code"] == account)
    assert fx["credit_minor"] + fx["debit_minor"] == 10000
    assert (await db.billing_instruments.find_one({"id": item["id"]}))["remaining_base_minor"] == 0
    assert await db.gl_journal_entries.find_one({"id": funding["id"]}, {"_id": 0}) == old
    assert (await s.reconcile(db, "A"))["healthy"]


async def test_funding_cannot_be_reused_with_new_reference_or_request(store):
    item, body, _ = await funded_issue(store, "gift_card_redemption")
    with pytest.raises(HTTPException) as error:
        await atomic(store, lambda session: s.issue(store, "A", ACTOR, body.model_copy(update={"request_id": uuid4(), "reference": "ikinci kart"}), session=session))
    assert error.value.status_code == 409
    assert await store.billing_instruments.count_documents({}) == 1


async def test_concurrent_redemptions_cannot_exceed_the_same_instrument(store):
    item, _ = await issued(store, "barter")
    results = await asyncio.gather(apply(store, item, application(amount_minor=7000)), apply(store, item, application(amount_minor=7000)), return_exceptions=True)
    assert sum(isinstance(row, dict) for row in results) == 1
    assert sum(isinstance(row, HTTPException) and row.status_code == 409 for row in results) == 1
    assert await store.payments.count_documents({}) == 1
    assert (await store.billing_instruments.find_one({"id": item["id"]}))["remaining_minor"] == 3000


async def test_first_concurrent_issues_cannot_allocate_one_funding_credit_twice(store):
    entry = await post_journal_entry(store, "A", date="2026-10-23", memo="Tek fonlama kaynağı",
        lines=[{"account_code": "102", "debit": 100}, {"account_code": "336", "credit": 100}], idempotency_key=str(uuid4()))
    def issue_body():
        return s.Issue(request_id=uuid4(), booking_id="b", kind="wallet", currency="TRY", amount_minor=10000,
            account_code="336", funding_entry_id=entry["id"], reference=str(uuid4()), reason="Belgeye bağlı fonlama")
    async def create(body):
        return await atomic(store, lambda session: s.issue(store, "A", ACTOR, body, session=session))
    results = await asyncio.gather(create(issue_body()), create(issue_body()), return_exceptions=True)
    assert sum(isinstance(row, dict) for row in results) == 1
    assert sum(isinstance(row, HTTPException) and row.status_code == 409 for row in results) == 1
    assert await store.billing_instruments.count_documents({}) == 1


@pytest.mark.parametrize("failure", ["cashier", "audit", "closed_period", "insufficient_points", "wrong_guest", "wrong_currency", "invoiced", "closed_folio", "future_cheque"])
async def test_failures_rollback_points_gl_payment_folio_and_instrument(store, monkeypatch, failure):
    db = store
    kind = "cheque_pending_clearance" if failure in {"cashier", "future_cheque"} else "loyalty_redemption"
    item, _ = await issued(db, kind, **({"due_on": "2026-10-25"} if failure == "future_cheque" else {}))
    if failure == "cashier":
        await db.cashier_shifts.update_one({"_id": "shift"}, {"$set": {"status": "closed"}})
    if failure == "audit":
        async def fail(*_, **__):
            raise RuntimeError("injected audit insert failure")
        monkeypatch.setattr(audit_chain, "append_audit_log", fail)
    if failure == "closed_period":
        from shared_kernel.gl_periods import ensure_calendar_year_periods
        await ensure_calendar_year_periods(db, "A", 2026)
        await db.gl_periods.update_many({"tenant_id": "A"}, {"$set": {"status": "closed"}})
    if failure == "insufficient_points":
        await db.loyalty_members.update_one({"guest_id": "g"}, {"$set": {"points_balance": 1}})
    if failure == "wrong_guest":
        await db.bookings.update_one({"id": "b"}, {"$set": {"guest_id": "other"}})
    if failure == "wrong_currency":
        await db.folios.update_one({"id": "f"}, {"$set": {"currency": "USD"}})
    if failure == "invoiced":
        await db.invoices.insert_one({"tenant_id": "A", "booking_id": "b", "status": "paid"})
    if failure == "closed_folio":
        await db.folios.update_one({"id": "f"}, {"$set": {"status": "closed"}})
    before = await db.loyalty_members.find_one({"guest_id": "g"})
    with pytest.raises((HTTPException, RuntimeError)):
        await apply(db, item, application())
    assert await db.payments.count_documents({}) == 0
    assert await db.gl_journal_entries.count_documents({}) == 0
    assert await db.loyalty_transactions.count_documents({}) == 0
    assert await db.loyalty_members.find_one({"guest_id": "g"}) == before
    assert (await db.billing_instruments.find_one({"id": item["id"]}))["remaining_minor"] == 10000
    assert await db.billing_instrument_operations.count_documents({}) == 1


async def test_idempotency_payload_tenant_and_missing_source_guards(store):
    item, _ = await issued(store, "write_off")
    body = application()
    await apply(store, item, body)
    with pytest.raises(HTTPException) as err:
        await apply(store, item, body.model_copy(update={"reason": "farklı açıklama"}))
    assert err.value.status_code == 409
    async with await store.client.start_session() as session:
        await s.prepare(store, "B")
        with pytest.raises(HTTPException) as err:
            await s.apply(store, "B", ACTOR, item["id"], application(), session=session, record_cash=None)
        assert err.value.status_code == 404
    with pytest.raises(HTTPException) as err:
        await s.apply(store, "A", ACTOR, item["id"], application(), session=None, record_cash=None)
    assert err.value.status_code == 503


async def test_own_reconciliation_detects_tamper_and_does_not_ignore_corrupt_cheques(store):
    item, _ = await issued(store, "cheque_pending_clearance")
    result = await apply(store, item, application())
    await store.payments.update_one({"id": result["payment_id"]}, {"$set": {"amount": 999}})
    assert not (await s.reconcile(store, "A"))["healthy"]
    with pytest.raises(HTTPException):
        await s.exclude_direct_cheques(store, "A", await store.payments.find({}).to_list(None))


@pytest.mark.parametrize("changes", [{"amount_minor": True}, {"amount_minor": 1.1}, {"kind": "wallet"},
    {"kind": "cheque_pending_clearance", "due_on": "2026-10-24", "currency": "EUR"}, {"currency": "JPY"}])
def test_schema_rejects_unbacked_or_inexact_money(changes):
    with pytest.raises((ValidationError, HTTPException)):
        s.Issue(**{"request_id": uuid4(), "booking_id": "b", "kind": "barter", "currency": "TRY", "amount_minor": 100,
            "account_code": "136", "reference": "doc", "reason": "documented", **changes})
