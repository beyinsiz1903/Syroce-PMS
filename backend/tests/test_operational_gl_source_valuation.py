"""Real local Mongo acceptance for append-only, source-bound FX corrections."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.integrations import operational_gl_valuation as v
from core.integrations.operational_gl_bridge import DEFAULT_MAPPING, OperationalGLBridgeError, post_direct_pos_to_gl
from shared_kernel.gl_posting import GLPostingError, normalize_journal_lines, post_journal_entry, verify_journal_entry_hash

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
DAY = "2026-10-01"
RATES = {"business_date": DAY, "base_currency": "TRY", "reference": "Synthetic presentation USD50 EUR55, not a market rate", "rates_to_try": {"USD": "50", "EUR": "55"}}
MAPPING = {**DEFAULT_MAPPING, "enabled": True, "security_deposit_account_code": "340"}


def plan(charges=(), payments=(), security=(), valuation=None):
    return v.build_plan(list(charges), list(payments), MAPPING, v.normalized_valuation(DAY, valuation or RATES), security)


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "-1", "0", "1000001", "55.1234567"])
def test_invalid_rates_fail_closed(rate):
    with pytest.raises(v.OperationalValuationError):
        v.normalized_valuation(DAY, {**RATES, "rates_to_try": {"EUR": rate}})


@pytest.mark.parametrize("day,base", [("2026-10-02", "TRY"), (DAY, "EUR")])
def test_rate_day_and_direction_are_explicit(day, base):
    with pytest.raises(v.OperationalValuationError):
        v.normalized_valuation(DAY, {**RATES, "business_date": day, "base_currency": base})


def test_currency_tax_refund_and_no_nominal_aggregation():
    p = plan([{"id": "t", "currency": "TRY", "total": 110, "tax_amount": 10},
              {"id": "e", "currency": "EUR", "total": 110, "tax_amount": 10}],
             [{"id": "p", "currency": "USD", "amount": 20, "method": "card"},
              {"id": "r", "currency": "USD", "amount": 5, "method": "card", "payment_type": "refund"}])
    assert p["charge_total_try"] == 6160 and p["payment_total_try"] == 750
    normalized, debit, credit = normalize_journal_lines(p["lines"])
    assert debit == credit == 6910
    assert [r["foreign_amount"] for r in normalized if r["account_code"] == "391" and r["currency"] == "EUR"] == [10]
    assert p["payment_by_account_minor"] == {"108": 75000}
    assert plan(list(reversed([{"id": "t", "currency": "TRY", "total": 110, "tax_amount": 10},
                               {"id": "e", "currency": "EUR", "total": 110, "tax_amount": 10}])),
                [{"id": "p", "currency": "USD", "amount": 15, "method": "card"}])["lines"] == p["lines"]


def test_actual_receipt_snapshot_must_match_day_and_cannot_hide_realised_fx():
    payment = {"id": "p", "currency": "USD", "amount": 20, "method": "card", "reporting_amount": 1000,
               "reporting_currency": "TRY", "exchange_rate_date": DAY}
    assert plan(payments=[payment])["payment_total_try"] == 1000
    with pytest.raises(v.OperationalValuationError, match="realised FX"):
        plan(payments=[{**payment, "reporting_amount": 1001}])
    with pytest.raises(v.OperationalValuationError, match="source day"):
        plan(payments=[{**payment, "exchange_rate_date": "2026-10-02"}])


@pytest.mark.parametrize("source", [
    {"id": "e", "currency": "EUR", "total": 10},
    {"id": "e", "currency": "EUR", "total": 10, "tax_amount": 11},
    {"id": "e", "currency": "UNKNOWN", "total": 10, "tax_amount": 0},
    {"currency": "EUR", "total": 10, "tax_amount": 0},
])
def test_unknown_tax_currency_or_source_identity_is_not_invented(source):
    with pytest.raises(v.OperationalValuationError):
        plan([source])


def test_security_receipt_refund_application_are_liability_not_revenue_or_double_cash():
    moves = [{"id": action, "fund_id": "f", "booking_id": "b", "currency": "TRY", "method": "cash",
              "action": action, "amount_minor": 10000} for action in ("received", "refund", "apply")]
    p = plan(security=moves)
    assert p["payment_total_try"] == 0 and p["charge_total_try"] == 0
    assert all(r["account_code"] != "600" for r in p["lines"])
    assert p["security_settlement_by_account_minor"] == {"100": 0}
    normalized, debit, credit = normalize_journal_lines(p["lines"])
    assert debit == credit == 300
    with pytest.raises(v.OperationalValuationError, match="realised FX"):
        plan(security=[{**moves[0], "action": "apply", "currency": "USD", "receipt_rate_to_try": "49"}])
    assert normalized


def test_accommodation_tax_is_not_silently_mixed_into_vat():
    source = {"id": "room", "currency": "TRY", "total": 111, "tax_amount": 11, "tax_breakdown": {"vat": 10, "accommodation_tax": 1}}
    with pytest.raises(v.OperationalValuationError, match="accommodation-tax"):
        plan([source])
    p = v.build_plan([source], [], {**MAPPING, "accommodation_tax_account_code": "360"}, v.normalized_valuation(DAY, RATES))
    assert next(r["credit"] for r in p["lines"] if r["account_code"] == "391") == 10
    assert next(r["credit"] for r in p["lines"] if r["account_code"] == "360") == 1


def test_receipt_rounding_is_never_lost_in_group_total():
    rates = {**RATES, "rates_to_try": {"EUR": "1.5"}}
    payments = [{"id": str(i), "currency": "EUR", "amount": .01, "method": "cash", "reporting_amount": .02,
                 "reporting_currency": "TRY", "exchange_rate_date": DAY} for i in range(3)]
    p = plan(payments=payments, valuation=rates)
    assert p["payment_total_try"] == .06
    # A larger rounding gap cannot fit into a GL foreign line's one-cent
    # contract. Reject it instead of inventing a rounding/gain account.
    with pytest.raises(v.OperationalValuationError):
        plan(payments=[{**payments[0], "id": str(i)} for i in range(20)], valuation=rates)


async def test_real_mongo_security_receipt_then_application_conserves_liability(ledger_db):
    db = ledger_db
    await seed(db, original=False)
    await db.security_funds.insert_one({"tenant_id": "hotel", "id": "fund", "booking_id": "b", "currency": "USD", "method": "card", "business_date": DAY})
    await db.security_fund_operations.insert_one({"_id": "received", "tenant_id": "hotel", "fund_id": "fund", "booking_id": "b", "currency": "USD", "action": "received", "amount_minor": 2000, "business_date": DAY})
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    next_day = "2026-10-02"
    await db.night_audit_runs.insert_one({"tenant_id": "hotel", "id": "next", "business_date": next_day, "status": "completed"})
    await db.security_fund_operations.insert_one({"_id": "apply", "tenant_id": "hotel", "fund_id": "fund", "booking_id": "b", "currency": "USD", "action": "apply", "amount_minor": 2000, "business_date": next_day})
    rates = {**RATES, "business_date": next_day}
    p = await v.preview_daily_valuation(db, "hotel", "next", rates)
    assert p["payment_total_try"] == 0
    assert p["lines"] == [
        {"account_code": "340", "debit": 1000, "memo": "İade edilebilir güvence yükümlülüğü", "currency": "USD", "foreign_amount": 20, "exchange_rate": "50"},
        {"account_code": "120", "credit": 1000, "memo": "Güvence apply; satış geliri değildir", "currency": "USD", "foreign_amount": 20, "exchange_rate": "50"}]
    with pytest.raises(v.OperationalValuationError, match="realised FX"):
        await v.preview_daily_valuation(db, "hotel", "next", {**rates, "rates_to_try": {"USD": "51", "EUR": "55"}})


async def seed(db, *, original=True):
    await db.gl_operational_mappings.insert_one({"tenant_id": "hotel", **MAPPING})
    await db.gl_accounts.insert_many([{"tenant_id": "hotel", "code": code, "active": True, "name": code} for code in ("100", "108", "102", "120", "600", "391", "340")])
    await db.night_audit_runs.insert_one({"tenant_id": "hotel", "id": "run", "business_date": DAY, "status": "completed", "gl_bridge_status": "posted" if original else "failed"})
    await db.folio_charges.insert_many([
        {"tenant_id": "hotel", "id": "c", "folio_id": "f", "business_date": DAY, "date": "2026-10-24", "currency": "EUR", "total": 110, "tax_amount": 10},
        {"tenant_id": "other", "id": "x", "business_date": DAY, "currency": "EUR", "total": 9999, "tax_amount": 0},
        {"tenant_id": "hotel", "id": "internal", "business_date": DAY, "currency": "EUR", "total": 500, "category": "split_adjustment"},
    ])
    await db.payments.insert_many([
        {"tenant_id": "hotel", "id": "p", "business_date": DAY, "currency": "EUR", "amount": 110, "method": "cash"},
        {"tenant_id": "hotel", "id": "not-cash", "business_date": DAY, "currency": "EUR", "amount": 999, "method": "city_ledger"},
    ])
    if original:
        old = await post_journal_entry(db, "hotel", date=DAY, memo="Preserved legacy nominal entry",
            lines=[{"account_code": "120", "debit": 110}, {"account_code": "600", "credit": 100}, {"account_code": "391", "credit": 10}],
            source="night_audit", source_ref="run", actor="old", idempotency_key="operational-daily:" + DAY)
        await db.night_audit_runs.update_one({"tenant_id": "hotel", "id": "run"}, {"$set": {"gl_journal_entry_id": old["id"]}})
        return old


async def test_real_mongo_single_atomic_correction_replay_conservation_and_sealed_manifest(ledger_db, monkeypatch):
    db = ledger_db
    old = await seed(db)
    before = deepcopy(old)
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    assert p["action"] == "correct" and p["charge_total_try"] == p["payment_total_try"] == 6050
    assert await db.gl_journal_entries.count_documents({}) == 1  # preview is read-only
    result = await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    assert result["status"] == "corrected"
    replay = await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    assert replay["status"] == "already_corrected" and replay["entry_id"] == result["entry_id"]
    assert await db.gl_journal_entries.count_documents({}) == 2
    assert await db.gl_journal_entries.find_one({"id": old["id"]}, {"_id": 0}) == before
    correction = await db.gl_journal_entries.find_one({"id": result["entry_id"]}, {"_id": 0})
    assert verify_journal_entry_hash(correction)
    corrupted = deepcopy(correction)
    corrupted["source_manifest"]["valuation"]["rates_to_try"]["EUR"] = "1"
    assert not verify_journal_entry_hash(corrupted)
    from domains.accounting import gl_router
    monkeypatch.setattr(gl_router, "db", db)
    report = await gl_router.operational_reconciliation(DAY, SimpleNamespace(tenant_id="hotel", role="admin"))
    assert report["folios"]["source_valuation_verified"], report
    assert report["folios"]["payment_total"] == report["folios"]["gl_total"] == 6050
    assert report["folios"]["variance"] == 0 and report["healthy"]
    await db.folio_charges.update_one({"tenant_id": "hotel", "id": "c"}, {"$set": {"total": 111}})
    report = await gl_router.operational_reconciliation(DAY, SimpleNamespace(tenant_id="hotel", role="admin"))
    assert not report["healthy"] and not report["folios"]["source_valuation_verified"]


async def test_changed_preview_or_closed_period_never_posts_partial_reversal(ledger_db):
    db = ledger_db
    await seed(db)
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    await db.payments.update_one({"id": "p"}, {"$set": {"amount": 100}})
    with pytest.raises(v.OperationalValuationError, match="Preview changed"):
        await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    assert await db.gl_journal_entries.count_documents({}) == 1
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    await db.gl_periods.update_many({"tenant_id": "hotel", "period_no": 10}, {"$set": {"status": "closed"}})
    with pytest.raises(GLPostingError):
        await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    assert await db.gl_journal_entries.count_documents({}) == 1


async def test_missing_sources_never_erase_nonzero_original_journal(ledger_db):
    original = await seed(ledger_db)
    await ledger_db.folio_charges.delete_many({"tenant_id": "hotel"})
    await ledger_db.payments.delete_many({"tenant_id": "hotel"})
    for operation in (lambda: v.preview_daily_valuation(ledger_db, "hotel", "run", RATES),
                      lambda: v.post_daily_valuation(ledger_db, "hotel", "run", RATES, "stale-hash", "operator")):
        with pytest.raises(v.OperationalValuationError, match="Source history missing"):
            await operation()
    assert await ledger_db.gl_journal_entries.count_documents({}) == 1
    assert await ledger_db.gl_journal_entries.find_one({"id": original["id"]}, {"_id": 0}) == original


async def test_genuine_empty_day_without_prior_money_is_still_no_activity(ledger_db):
    await seed(ledger_db, original=False)
    await ledger_db.folio_charges.delete_many({"tenant_id": "hotel"})
    await ledger_db.payments.delete_many({"tenant_id": "hotel"})
    preview = await v.preview_daily_valuation(ledger_db, "hotel", "run", RATES)
    assert preview["action"] == "no_activity" and preview["lines"] == []


async def test_committed_correction_response_failure_recovers_link_without_double_post(ledger_db, monkeypatch):
    db = ledger_db
    await seed(db)
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    collection = db.night_audit_runs
    wrapped = SimpleNamespace(**{name: db[name] for name in ("gl_operational_mappings", "gl_accounts", "gl_periods", "folio_charges", "payments", "security_fund_operations", "security_funds", "gl_journal_entries", "gl_counters", "gl_sequence_reservations")},
        night_audit_runs=SimpleNamespace(find_one=collection.find_one, update_one=AsyncMock(side_effect=RuntimeError("response failure"))))
    with pytest.raises(RuntimeError):
        await v.post_daily_valuation(wrapped, "hotel", "run", RATES, p["preview_hash"], "operator")
    assert await db.gl_journal_entries.count_documents({}) == 2
    result = await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    assert result["status"] == "already_corrected"
    assert await db.gl_journal_entries.count_documents({}) == 2


async def test_no_original_posts_once_and_other_tenant_cannot_access_run(ledger_db):
    db = ledger_db
    await seed(db, original=False)
    with pytest.raises(v.OperationalValuationError, match="not found"):
        await v.preview_daily_valuation(db, "other", "run", RATES)
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    assert p["action"] == "post"
    result = await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    assert result["status"] == "posted"
    assert (await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator"))["status"] == "already_posted"
    assert await db.gl_journal_entries.count_documents({}) == 1


async def test_routes_enforce_accounting_role(ledger_db, monkeypatch):
    from domains.accounting import gl_router as gl
    monkeypatch.setattr(gl, "db", ledger_db)
    with pytest.raises(HTTPException) as error:
        await gl.preview_operational_valuation("run", gl.OperationalValuationIn(**RATES), SimpleNamespace(tenant_id="hotel", role="reception"))
    assert error.value.status_code == 403


async def test_concurrent_identical_corrections_do_not_duplicate_money(ledger_db):
    db = ledger_db
    await seed(db)
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    results = await asyncio.gather(*[v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator") for _ in range(2)], return_exceptions=True)
    assert any(isinstance(r, dict) for r in results)
    assert await db.gl_journal_entries.count_documents({}) == 2
    assert (await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator"))["status"] == "already_corrected"


async def test_concurrent_different_rates_cannot_adopt_another_payloads_journal(ledger_db):
    db = ledger_db
    await seed(db)
    second = {**RATES, "rates_to_try": {"EUR": "56"}}
    p1, p2 = [await v.preview_daily_valuation(db, "hotel", "run", r) for r in (RATES, second)]
    results = await asyncio.gather(v.post_daily_valuation(db, "hotel", "run", RATES, p1["preview_hash"], "operator"),
        v.post_daily_valuation(db, "hotel", "run", second, p2["preview_hash"], "operator"), return_exceptions=True)
    assert len([r for r in results if isinstance(r, dict)]) == 1
    assert await db.gl_journal_entries.count_documents({}) == 2


async def test_mapping_omission_preserves_new_accounts_and_rejects_asset_as_liability(ledger_db, monkeypatch):
    from domains.accounting import gl_router as gl
    await seed(ledger_db)
    await ledger_db.gl_operational_mappings.update_one({"tenant_id": "hotel"}, {"$set": {"created_at": "2026-01-01"}})
    monkeypatch.setattr(gl, "db", ledger_db)
    # The original mapping fixture's 340 must be a real liability account.
    await ledger_db.gl_accounts.update_one({"tenant_id": "hotel", "code": "340"}, {"$set": {"type": "liability"}})
    user = SimpleNamespace(tenant_id="hotel", role="finance", id="finance")
    result = await gl.update_operational_gl_mapping(gl.OperationalMappingIn(enabled=True), user)
    assert result["mapping"]["security_deposit_account_code"] == "340"
    with pytest.raises(HTTPException):
        await gl.update_operational_gl_mapping(gl.OperationalMappingIn(security_deposit_account_code="100"), user)


@pytest.mark.parametrize("code,method", [("USD", "cash"), ("TRY", "gift_card")])
async def test_direct_pos_never_assumes_foreign_base_is_try_or_unknown_method_is_bank(ledger_db, code, method):
    await seed(ledger_db, original=False)
    with pytest.raises(OperationalGLBridgeError):
        await post_direct_pos_to_gl(ledger_db, "hotel", transaction={"id": "txn", "order_id": "order", "transaction_date": DAY,
            "total_amount": 110, "tax_amount": 10, "currency": code, "payment_method": method}, order={}, posted_to_folio=False, actor="cashier")
    assert await ledger_db.gl_journal_entries.count_documents({}) == 0


async def test_reversed_correction_cannot_be_certified_and_keeps_foreign_positions(ledger_db, monkeypatch):
    from domains.accounting import gl_router as gl
    db = ledger_db
    await seed(db)
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    result = await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    monkeypatch.setattr(gl, "db", db)
    user = SimpleNamespace(tenant_id="hotel", role="finance", id="finance")
    reversal = await gl.reverse_journal(result["entry_id"], gl.JournalReversalIn(date=DAY, reason="Source correction reversal acceptance", idempotency_key="reverse-correction-acceptance"), user)
    assert any(r.get("currency") == "EUR" for r in reversal["entry"]["lines"])
    with pytest.raises(v.OperationalValuationError, match="manual reconciliation"):
        await v.preview_daily_valuation(db, "hotel", "run", RATES)


async def test_linked_legacy_original_without_daily_key_is_corrected_not_double_posted(ledger_db):
    db = ledger_db
    await seed(db, original=False)
    old = await post_journal_entry(db, "hotel", date=DAY, memo="Legacy source without daily key", lines=[
        {"account_code": "120", "debit": 110}, {"account_code": "600", "credit": 110}], source="night_audit", source_ref="run")
    await db.night_audit_runs.update_one({"id": "run"}, {"$set": {"gl_journal_entry_id": old["id"]}})
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    assert p["action"] == "correct" and p["original_entry_id"] == old["id"]
    await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "operator")
    assert await db.gl_journal_entries.count_documents({"source": "night_audit"}) == 1


async def test_ambiguous_duplicate_source_journals_fail_closed(ledger_db):
    db = ledger_db
    await seed(db)
    await post_journal_entry(db, "hotel", date=DAY, memo="Duplicate legacy source", lines=[
        {"account_code": "120", "debit": 110}, {"account_code": "600", "credit": 110}], source="night_audit", source_ref="run")
    with pytest.raises(v.OperationalValuationError, match="Multiple original"):
        await v.preview_daily_valuation(db, "hotel", "run", RATES)
    assert await db.gl_journal_entries.count_documents({}) == 2


def test_non_cash_adjustment_has_no_cash_or_tax_lines_and_supports_signed_rate_corrections():
    rows = [{"id": "comp", "currency": "TRY", "amount": 8400, "method": "discount", "payment_type": "comp_adjustment"},
            {"id": "correction", "currency": "EUR", "amount": -10, "method": "discount", "payment_type": "rate_correction"}]
    with pytest.raises(v.OperationalValuationError, match="sales-adjustment account"):
        plan(payments=rows)
    p = v.build_plan([], rows, {**MAPPING, "adjustment_account_code": "611"}, v.normalized_valuation(DAY, RATES))
    assert p["adjustment_total_try"] == 7850 and p["payment_total_try"] == 0
    assert p["payment_by_account_minor"] == {} and p["charge_total_try"] == 0
    assert {r["account_code"] for r in p["lines"]} == {"611", "120"}
    assert {r["kind"] for r in p["manifest"]["sources"]} == {"adjustment"}
    assert p["manifest"]["mapping"]["adjustment_account_code"] == "611"
    _, debit, credit = normalize_journal_lines(p["lines"])
    assert debit == credit == 8950
    with pytest.raises(v.OperationalValuationError, match="adjustment type"):
        v.build_plan([], [{**rows[0], "payment_type": "unknown"}], {**MAPPING, "adjustment_account_code": "611"}, v.normalized_valuation(DAY, RATES))
    with pytest.raises(v.OperationalValuationError, match="separate contra-sales"):
        v.build_plan([], rows, {**MAPPING, "adjustment_account_code": "100"}, v.normalized_valuation(DAY, RATES))


def test_optional_new_mapping_does_not_change_sealed_days_without_adjustments():
    charges = [{"id": "room", "currency": "EUR", "total": 110, "tax_amount": 10}]
    old = v.build_plan(charges, [], {k: value for k, value in MAPPING.items() if k != "adjustment_account_code"}, v.normalized_valuation(DAY, RATES))
    new = v.build_plan(charges, [], {**MAPPING, "adjustment_account_code": "611"}, v.normalized_valuation(DAY, RATES))
    assert old["manifest"] == new["manifest"] and old["lines"] == new["lines"]


async def test_real_mongo_adjustment_is_source_bound_deduplicated_replay_safe_and_reconciles(ledger_db, monkeypatch):
    from domains.accounting import gl_router as gl
    db = ledger_db
    old = await seed(db)
    await db.gl_accounts.insert_one({"tenant_id": "hotel", "code": "611", "active": True, "type": "revenue", "normal_balance": "debit"})
    await db.gl_operational_mappings.update_one({"tenant_id": "hotel"}, {"$set": {"adjustment_account_code": "611"}})
    adjustment = {"tenant_id": "hotel", "id": "comp", "booking_id": "b", "folio_id": "f", "business_date": DAY,
                  "amount": 10, "currency": "EUR", "method": "discount", "payment_type": "comp_adjustment", "idempotency_key": "same-comp"}
    await db.payments.insert_many([adjustment, {**adjustment, "id": "retry"},
        {**adjustment, "id": "pending", "idempotency_key": "pending", "status": "pending"},
        {**adjustment, "id": "other", "tenant_id": "other"}])
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    assert p["adjustment_total_try"] == 550 and p["payment_total_try"] == 6050
    assert sum(r["kind"] == "adjustment" for r in p["manifest"]["sources"]) == 1
    result = await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "finance")
    replay = await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "finance")
    assert result["entry_id"] == replay["entry_id"] and replay["status"] == "already_corrected"
    assert await db.gl_journal_entries.find_one({"id": old["id"]}, {"_id": 0}) == old
    monkeypatch.setattr(gl, "db", db)
    report = await gl.operational_reconciliation(DAY, SimpleNamespace(tenant_id="hotel", role="finance"))
    assert report["healthy"] and report["folios"]["non_cash_adjustments_try"] == 550
    assert report["folios"]["payment_total"] == report["folios"]["gl_total"] == 6050
    await db.payments.update_many({"tenant_id": "hotel", "idempotency_key": "same-comp"}, {"$set": {"amount": 11}})
    report = await gl.operational_reconciliation(DAY, SimpleNamespace(tenant_id="hotel", role="finance"))
    assert not report["healthy"] and any(b["code"] == "non_cash_adjustments_unposted" for b in report["blockers"])


async def test_real_mongo_discount_only_day_is_not_falsely_healthy_when_unposted(ledger_db, monkeypatch):
    from domains.accounting import gl_router as gl
    db = ledger_db
    await db.gl_operational_mappings.insert_one({"tenant_id": "hotel", **MAPPING})
    await db.payments.insert_one({"tenant_id": "hotel", "id": "comp", "business_date": DAY,
        "amount": 100, "currency": "TRY", "method": "discount", "payment_type": "comp_adjustment"})
    monkeypatch.setattr(gl, "db", db)
    report = await gl.operational_reconciliation(DAY, SimpleNamespace(tenant_id="hotel", role="finance"))
    assert not report["healthy"] and report["folios"]["payment_total"] == 0
    assert report["folios"]["non_cash_adjustments_by_currency"] == {"TRY": 100}
    assert report["folios"]["non_cash_adjustments_try"] is None
    await db.gl_accounts.insert_many([
        {"tenant_id": "hotel", "code": "120", "active": True},
        {"tenant_id": "hotel", "code": "611", "active": True}])
    await db.gl_operational_mappings.update_one({"tenant_id": "hotel"}, {"$set": {"adjustment_account_code": "611"}})
    await db.night_audit_runs.insert_one({"tenant_id": "hotel", "id": "run", "business_date": DAY, "status": "completed"})
    p = await v.preview_daily_valuation(db, "hotel", "run", RATES)
    assert p["action"] == "post" and p["payment_total_try"] == p["charge_total_try"] == 0
    await v.post_daily_valuation(db, "hotel", "run", RATES, p["preview_hash"], "u")
    report = await gl.operational_reconciliation(DAY, SimpleNamespace(tenant_id="hotel", role="finance"))
    assert report["healthy"] and report["folios"]["payment_total"] == report["folios"]["gl_total"] == 0
    assert report["folios"]["non_cash_adjustments_try"] == 100


@pytest.mark.parametrize("code,type_,normal", [("100", "asset", "debit"), ("611", "revenue", "credit"), ("600", "revenue", "debit")])
async def test_adjustment_mapping_rejects_cash_normal_revenue_or_reused_accounts(ledger_db, monkeypatch, code, type_, normal):
    from domains.accounting import gl_router as gl
    db = ledger_db
    await seed(db)
    await db.gl_accounts.update_one({"tenant_id": "hotel", "code": "340"}, {"$set": {"type": "liability", "normal_balance": "credit"}})
    await db.gl_accounts.update_one({"tenant_id": "hotel", "code": code},
        {"$set": {"active": True, "type": type_, "normal_balance": normal}}, upsert=True)
    monkeypatch.setattr(gl, "db", db)
    with pytest.raises(HTTPException) as exc:
        await gl.update_operational_gl_mapping(gl.OperationalMappingIn(adjustment_account_code=code), SimpleNamespace(tenant_id="hotel", role="finance", id="u"))
    assert exc.value.status_code == 409
    assert "İkram/indirim" in exc.value.detail


async def test_adjustment_mapping_accepts_separate_contra_sales_account_and_logs_it(ledger_db, monkeypatch):
    from domains.accounting import gl_router as gl
    db = ledger_db
    await seed(db)
    await db.gl_accounts.update_one({"tenant_id": "hotel", "code": "340"}, {"$set": {"type": "liability", "normal_balance": "credit"}})
    await db.gl_accounts.insert_one({"tenant_id": "hotel", "code": "611", "active": True, "type": "revenue", "normal_balance": "debit"})
    monkeypatch.setattr(gl, "db", db)
    monkeypatch.setattr(gl, "log_audit_event", AsyncMock())
    result = await gl.update_operational_gl_mapping(gl.OperationalMappingIn(adjustment_account_code="611"), SimpleNamespace(tenant_id="hotel", role="finance", id="u"))
    assert result["mapping"]["adjustment_account_code"] == "611" and result["mapping"]["enabled"]
    assert gl.log_audit_event.await_args.kwargs["after_value"]["adjustment_account_code"] == "611"
