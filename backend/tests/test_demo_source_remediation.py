"""Isolated replica acceptance for the approved synthetic legacy reconstruction."""
import asyncio
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core import audit_chain
from core.integrations import operational_gl_valuation as valuation
from core.integrations.operational_gl_bridge import DEFAULT_MAPPING
from modules.pms_core import demo_source_remediation as r
from modules.pms_core.cari_receivable_reporting import account_positions
from modules.pms_core.revenue_report import build_revenue_report
from routers.reservation_detail import DemoSourceRemediationIn
from shared_kernel.gl_posting import compute_journal_entry_hash, normalize_journal_lines, post_journal_entry, verify_journal_entry_hash

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(id="demo-admin", name="Demo Operator", role="admin", tenant_id=r.TENANT)


def data(plan, **extra):
    return DemoSourceRemediationIn(request_id=extra.pop("request_id", uuid4()),
        source_fingerprint=plan["source_fingerprint"], reason="Kullanıcı onaylı, örnek değerleri açık işaretli Demo Hotel yeniden kurma.",
        confirmation="RECONSTRUCT_SYNTHETIC_DEMO_100001_ONLY", **extra)


async def seed(db):
    await db.tenants.insert_one({"id": r.TENANT, "hotel_id": "100001", "property_name": "Syroce Demo Hotel"})
    await db.tenant_settings.insert_one({"tenant_id": r.TENANT, "business_date": "2026-10-24"})
    await db.exely_connections.insert_one({"tenant_id": r.TENANT, "id": "connection", "hotel_code": "501694", "mode": "sandbox", "is_active": True, "ari_write_enabled": False, "auto_sync_reservations": False})
    for index, bid in enumerate(r.HOLDS):
        await db.bookings.insert_one({"tenant_id": r.TENANT, "id": bid, "status": "pending_mapping", "is_inventory_hold": True,
            "booking_source": "ota_unmatched_hold", "external_reservation_id": r.EXTERNAL[0 if index < 2 else 1], "source": {"provider": "exely"}, "check_in": "2026-10-15"})
    for index, external in enumerate(r.EXTERNAL):
        await db.exely_reservations.insert_one({"tenant_id": r.TENANT, "id": "inbox-" + str(index), "external_id": external,
            "state": "confirmed", "pms_status": "pending_mapping", "delivery_confirmed": False})
    for code in ("USD", "EUR"):
        for pid, amount in zip([pid for pid, currency in r.FX_IDS.items() if currency == code], (100, -40, -60), strict=True):
            await db.payments.insert_one({"tenant_id": r.TENANT, "id": pid, "booking_id": "fx-" + code, "currency": code, "amount": amount,
                "business_date": "2026-10-24", "method": "card" if code == "USD" else "bank_transfer", "status": "paid",
                "payment_type": "refund" if amount < 0 else "deposit", "voided": False})
    await db.cashier_shifts.insert_one({"tenant_id": r.TENANT, "id": "shift", "status": "open", "business_date": "2026-10-24",
        "transactions": [{"id": "preserved", "ref_id": "other", "amount": 1}], "cash_in": 1, "cash_out": 0})
    for cid in r.COMP_IDS:
        await db.extra_charges.insert_one({"tenant_id": r.TENANT, "id": cid, "booking_id": "comp", "is_complimentary": True,
            "complimentary_scope": "full", "complimentary_original_amount": 20, "total": 0, "amount": 0,
            "business_date": "2026-10-05", "category": "food", "currency": "USD"})
    await db.cari_accounts.insert_one({"tenant_id": r.TENANT, "id": r.ACCOUNT, "balance": 4503})
    for index, amount in enumerate((100, 4400, 1, 1, 1, 1, 1, 1)):
        await db.cari_transactions.insert_one({"tenant_id": r.TENANT, "id": "debit-" + str(index), "cari_account_id": r.ACCOUNT,
            "transaction_type": "charge", "amount": amount, "created_at": "2026-08-01T10:00:00Z"})
    for index, kind in enumerate(("payment", "transfer_out", "transfer_out")):
        await db.cari_transactions.insert_one({"tenant_id": r.TENANT, "id": "credit-" + str(index), "cari_account_id": r.ACCOUNT,
            "transaction_type": kind, "amount": 1, "created_at": "2026-08-02T10:00:00Z"})
    amounts = [150, 150, 150, 8000, 1200, 11, 1, 1000, 1, 1, 1, 1, 3955]
    for pid, amount in zip(r.SEPTEMBER_IDS, amounts, strict=True):
        await db.payments.insert_one({"tenant_id": r.TENANT, "id": pid, "booking_id": "old-" + pid,
            "currency": "TRY" if pid in {r.RECLASS_PAYMENT, r.SEPTEMBER_IDS[3]} else None,
            "amount": amount, "business_date": "2026-09-05", "method": "cash", "status": "paid",
            "processed_at": "2026-09-27T13:42:15Z" if pid == r.RECLASS_PAYMENT else "2026-08-01T10:00:00Z"})
    lines, debit, credit = normalize_journal_lines([{"account_code": "100", "debit": 1200}, {"account_code": "120", "credit": 1200}])
    original = {"tenant_id": r.TENANT, "id": r.RECLASS_ENTRY, "date": "2026-09-27", "entry_no": "YEV-2026-00000001",
        "posting_sequence": 1, "fiscal_year": 2026, "source": "night_audit", "source_ref": r.RECLASS_RUN,
        "status": "posted", "idempotency_key": "operational-daily:2026-09-27", "lines": lines,
        "total_debit": debit, "total_credit": credit, "total_debit_minor": 120000, "total_credit_minor": 120000}
    original["entry_hash"] = compute_journal_entry_hash(original)
    await db.gl_journal_entries.insert_one(deepcopy(original))
    await db.gl_counters.insert_one({"_id": f"gl-journal-counter:{r.TENANT}:2026", "tenant_id": r.TENANT, "value": 1})
    await db.gl_sequence_reservations.insert_one({"_id": f"gl-journal-sequence:{r.TENANT}:2026:00000001", "tenant_id": r.TENANT,
        "fiscal_year": 2026, "sequence": 1, "entry_id": r.RECLASS_ENTRY, "status": "posted"})
    await db.night_audit_runs.insert_one({"tenant_id": r.TENANT, "id": r.RECLASS_RUN, "status": "completed", "business_date": "2026-09-27", "gl_bridge_status": "posted", "gl_journal_entry_id": r.RECLASS_ENTRY})
    await db.gl_operational_mappings.insert_one({"tenant_id": r.TENANT, **DEFAULT_MAPPING, "enabled": True, "accommodation_tax_account_code": "360.02"})
    await db.gl_accounts.insert_many([{"tenant_id": r.TENANT, "code": code, "active": True, "name": code} for code in ("100", "120", "600", "391", "360.02")])
    previous = ""
    for seq in range(1, 70):
        entry = {"tenant_id": r.TENANT, "id": "old-audit-" + str(seq), "seq": seq, "prev_hash": previous, "action": "reservation_created", "timestamp": "2026-10-24T10:00:00Z"}
        entry["record_hash"] = audit_chain.compute_record_hash(entry, seq, previous)
        previous = entry["record_hash"]
        entry.update(ip_address="192.0.2.1", user_agent="late-metadata")
        await db.audit_logs.insert_one(entry)
    await db.audit_chain_state.insert_one({"_id": r.TENANT, "seq": 69, "last_hash": previous})
    return original


@pytest.fixture(autouse=True)
def isolated(monkeypatch, ledger_db):
    monkeypatch.setattr(audit_chain, "_system_db", lambda: ledger_db)
    from modules.pms_core import deposit_operations
    monkeypatch.setattr(deposit_operations, "refresh_reports", AsyncMock())


async def test_atomic_demo_reconstruction_preserves_amounts_preimages_audit_and_replays_once(ledger_db):
    db = ledger_db
    original = await seed(db)
    before_payments = await db.payments.find({}).to_list(None)
    before_audit = await db.audit_logs.find({}).to_list(None)
    p = await r.preview(db, r.TENANT)
    assert len(p["documents"]) == 43 and len(p["cashier"]["append"]) == 6
    assert len(p["audit_incident"]["findings"]) == 69
    assert await db.demo_source_preimages.count_documents({}) == 0
    request = data(p)
    result = await r.apply(db, db.client, USER, request)
    assert result["applied"] and not result["historical_source_verified"]
    assert result["request_id"] == str(request.request_id)
    assert await db.demo_source_preimages.count_documents({}) == 43
    for old in before_payments:
        new = await db.payments.find_one({"id": old["id"]})
        assert new["amount"] == old["amount"] and new["id"] == old["id"]
    assert await db.gl_journal_entries.find_one({"id": original["id"]}, {"_id": 0}) == original
    assert await db.audit_logs.find({"seq": {"$lte": 69}}).to_list(None) == before_audit
    verification = await audit_chain.verify_chain(r.TENANT)
    assert len(verification["breaks"]) == 69 and not verification["ok"]
    shift = await db.cashier_shifts.find_one({"id": "shift"})
    assert len(shift["transactions"]) == 7 and shift["cash_in"] == 1 and shift["cash_out"] == 0
    assert sum(r.minor(x["amount"]) * (1 if x["direction"] == "in" else -1) for x in shift["transactions"][1:]) == 0
    again = await r.apply(db, db.client, USER, request)
    assert again["replayed"] and await db.demo_source_remediations.count_documents({}) == 1
    assert await db.demo_source_preimages.count_documents({}) == 43
    assert (await r.preview(db, r.TENANT))["already_applied"]
    with pytest.raises(HTTPException, match="409"):
        await r.apply(db, db.client, USER, request.model_copy(update={"reason": "A different reconstruction instruction"}))
    accounts = await db.cari_accounts.find({}).to_list(None)
    rows = await db.cari_transactions.find({}).to_list(None)
    positions, failed, issues = account_positions(accounts, rows, source="cari_accounts", fallback_currency="TRY", today=date(2026, 10, 24))
    assert not failed and not issues and sum(x["balance"] for x in positions) == 4503
    assert all(not x["age_unknown"] and x["demo_reconstructed"] and not x["historical_source_verified"] for x in positions)
    comp = await db.extra_charges.find({}).to_list(None)
    report = build_revenue_report(comp, date(2026, 10, 1), date(2026, 10, 31))
    assert report["reconciliation"]["tax_unknown_count"] == 0
    assert report["reconciliation"]["demo_reconstructed_count"] == 8
    assert not report["reconciliation"]["historical_source_verified"]


async def test_failure_rolls_back_every_document_cashier_preimage_receipt_and_chain(ledger_db, monkeypatch):
    db = ledger_db
    await seed(db)
    before = await db.payments.find({}).to_list(None)
    plan = await r.preview(db, r.TENANT)
    async def fail(*_args, **_kw):
        raise RuntimeError("injected chain failure")
    monkeypatch.setattr(r, "append_audit_log", fail)
    with pytest.raises(RuntimeError, match="injected"):
        await r.apply(db, db.client, USER, data(plan))
    assert await db.payments.find({}).to_list(None) == before
    assert await db.demo_source_preimages.count_documents({}) == 0
    assert await db.demo_source_remediations.count_documents({}) == 0
    assert len((await db.cashier_shifts.find_one({"id": "shift"}))["transactions"]) == 1
    assert await db.audit_logs.count_documents({}) == 69


async def test_wrong_tenant_live_provider_stale_or_financial_hold_fail_closed(ledger_db):
    db = ledger_db
    await seed(db)
    with pytest.raises(HTTPException) as wrong:
        await r.preview(db, "real-hotel")
    assert wrong.value.status_code == 404
    p = await r.preview(db, r.TENANT)
    await db.payments.update_one({"id": r.SEPTEMBER_IDS[0]}, {"$set": {"amount": 151}})
    with pytest.raises(HTTPException):
        await r.apply(db, db.client, USER, data(p))
    await db.payments.update_one({"id": r.SEPTEMBER_IDS[0]}, {"$set": {"amount": 150}})
    await db.folios.insert_one({"tenant_id": r.TENANT, "id": "new-folio", "booking_id": r.HOLDS[0]})
    with pytest.raises(HTTPException, match="Finansal"):
        await r.preview(db, r.TENANT)
    await db.folios.delete_one({"id": "new-folio"})
    await db.exely_connections.update_one({"id": "connection"}, {"$set": {"ari_write_enabled": True}})
    with pytest.raises(HTTPException, match="kapalı"):
        await r.preview(db, r.TENANT)
    assert await db.demo_source_preimages.count_documents({}) == 0


async def test_demo_reclassification_has_sealed_proof_preserves_original_and_zeroes_only_wrong_day(ledger_db):
    db = ledger_db
    original = await seed(db)
    rates = {"business_date": "2026-09-27", "base_currency": "TRY", "rates_to_try": {}, "reference": "Approved demo reclassification, not verified historical lineage"}
    with pytest.raises(valuation.OperationalValuationError, match="Source history missing"):
        await valuation.preview_daily_valuation(db, r.TENANT, r.RECLASS_RUN, rates)
    p = await r.preview(db, r.TENANT)
    await r.apply(db, db.client, USER, data(p))
    preview = await valuation.preview_daily_valuation(db, r.TENANT, r.RECLASS_RUN, rates)
    assert preview["action"] == "correct" and preview["payment_total_try"] == 0
    assert preview["manifest"]["sources"][0]["kind"] == "demo_reclassified_payment"
    result = await valuation.post_daily_valuation(db, r.TENANT, r.RECLASS_RUN, rates, preview["preview_hash"], USER.id)
    correction = await db.gl_journal_entries.find_one({"id": result["entry_id"]}, {"_id": 0})
    assert verify_journal_entry_hash(correction)
    assert await db.gl_journal_entries.find_one({"id": r.RECLASS_ENTRY}, {"_id": 0}) == original
    assert sum(r.minor(x.get("debit")) - r.minor(x.get("credit")) for x in correction["lines"]) == 0
    replay = await valuation.preview_daily_valuation(db, r.TENANT, r.RECLASS_RUN, rates)
    assert replay["action"] == "already_corrected"
    await db.payments.update_one({"id": r.RECLASS_PAYMENT}, {"$set": {"amount": 1201}})
    with pytest.raises(HTTPException, match="kaynağı değişti"):
        await valuation.preview_daily_valuation(db, r.TENANT, r.RECLASS_RUN, rates)


async def test_mapping_archive_is_demo_only_and_never_source_cancellation_or_ack(ledger_db, monkeypatch):
    from core.channel_mapping_issues import load_mapping_issues
    from domains.channel_manager.providers.exely import pms_lifecycle
    db = ledger_db
    await seed(db)
    assert len(await load_mapping_issues(r.TENANT, "2026-10-24", database=db)) >= 2
    await r.apply(db, db.client, USER, data(await r.preview(db, r.TENANT)))
    assert await load_mapping_issues(r.TENANT, "2026-10-24", database=db) == []
    sources = await db.exely_reservations.find({}).to_list(None)
    assert all(x["state"] == "confirmed" and not x["delivery_confirmed"] for x in sources)
    monkeypatch.setattr(pms_lifecycle, "db", db)
    outcome = await pms_lifecycle.process_reservation_version(r.TENANT, {"external_id": r.EXTERNAL[0]})
    assert not outcome["success"] and outcome["provider_write_count"] == 0
    assert outcome["reason"] == "SYNTHETIC_DEMO_SOURCE_ARCHIVED"


@pytest.mark.parametrize("changed", [{"checked_in_at": "2026-10-15"}, {"actual_check_out": "2026-10-16"}, {"room_id": "real-room"}])
async def test_accepted_stay_is_never_archived_as_an_unaccepted_hold(ledger_db, changed):
    await seed(ledger_db)
    await ledger_db.bookings.update_one({"id": r.HOLDS[0]}, {"$set": changed})
    with pytest.raises(HTTPException, match="boş bir eşleştirme"):
        await r.preview(ledger_db, r.TENANT)
    assert await ledger_db.demo_source_preimages.count_documents({}) == 0


async def test_real_room_lock_cannot_be_discarded_by_demo_archive(ledger_db):
    await seed(ledger_db)
    await ledger_db.room_night_locks.insert_one({"tenant_id": r.TENANT, "booking_id": r.HOLDS[0], "room_id": "real-room", "lock_type": "booking"})
    with pytest.raises(HTTPException, match="Fiziksel oda kilidi"):
        await r.preview(ledger_db, r.TENANT)


@pytest.mark.parametrize("same_request", [True, False])
async def test_concurrent_requests_commit_one_reconstruction_only(ledger_db, same_request):
    db = ledger_db
    await seed(db)
    await db.reservation_financial_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True)
    plan = await r.preview(db, r.TENANT)
    request = data(plan)
    outcomes = await asyncio.gather(r.apply(db, db.client, USER, request),
        r.apply(db, db.client, USER, request if same_request else data(plan)), return_exceptions=True)
    if same_request:
        assert all(isinstance(x, dict) for x in outcomes), outcomes
        assert sorted(x["replayed"] for x in outcomes) == [False, True]
    else:
        assert sum(isinstance(x, dict) for x in outcomes) == 1, outcomes
        assert any(isinstance(x, HTTPException) and x.status_code == 409 for x in outcomes), outcomes
    assert await db.demo_source_remediations.count_documents({}) == 1
    assert await db.demo_source_preimages.count_documents({}) == 43
    assert len((await db.cashier_shifts.find_one({"id": "shift"}))["transactions"]) == 7


async def test_both_september_days_reconcile_with_explicit_demo_warning_and_intact_originals(ledger_db, monkeypatch):
    from domains.accounting import gl_router
    db = ledger_db
    day27_original = await seed(db)
    await db.folio_charges.insert_one({"tenant_id": r.TENANT, "id": "sept-charge", "business_date": "2026-09-05",
        "currency": "TRY", "total": 5500, "tax_amount": 545.05, "tax_breakdown": {"vat": 490.55, "accommodation_tax": 54.5}})
    run5 = "day5-run"
    original = await post_journal_entry(db, r.TENANT, date="2026-09-05", memo="Preserved legacy nominal journal",
        lines=[{"account_code": "100", "debit": 13421}, {"account_code": "120", "credit": 13421}],
        source="night_audit", source_ref=run5, actor="legacy", idempotency_key="operational-daily:2026-09-05")
    original = await db.gl_journal_entries.find_one({"id": original["id"]}, {"_id": 0})
    await db.night_audit_runs.insert_one({"tenant_id": r.TENANT, "id": run5, "business_date": "2026-09-05", "status": "completed", "gl_bridge_status": "posted", "gl_journal_entry_id": original["id"]})
    await r.apply(db, db.client, USER, data(await r.preview(db, r.TENANT)))
    monkeypatch.setattr(gl_router, "db", db)
    for day, run, expected in [("2026-09-05", run5, 14621), ("2026-09-27", r.RECLASS_RUN, 0)]:
        rates = {"business_date": day, "base_currency": "TRY", "rates_to_try": {}, "reference": r.NOTICE}
        p = await valuation.preview_daily_valuation(db, r.TENANT, run, rates)
        assert p["payment_total_try"] == expected
        await valuation.post_daily_valuation(db, r.TENANT, run, rates, p["preview_hash"], USER.id)
        report = await gl_router.operational_reconciliation(day, USER)
        assert report["healthy"] and report["folios"]["variance"] == 0, report
        assert report["folios"]["source_valuation_verified"]
        assert {x["code"] for x in report["warnings"]} >= {"demo_reconstructed_sources"}
        assert next(x for x in report["warnings"] if x["code"] == "demo_reconstructed_sources")["historical_source_verified"] is False
    for old in (original, day27_original):
        assert await db.gl_journal_entries.find_one({"id": old["id"]}, {"_id": 0}) == old
    assert await db.gl_journal_entries.count_documents({"source": "night_audit_correction"}) == 2
    assert not (await audit_chain.verify_chain(r.TENANT))["ok"]  # never turn documented old drift into a pass


def test_archive_marker_cannot_hide_other_demo_bookings_or_real_hotels():
    from core.channel_mapping_issues import group_mapping_issues
    row = {"tenant_id": r.TENANT, "id": r.HOLDS[0], "status": "archived_demo", "is_inventory_hold": True,
           "demo_reconstruction": r.provenance("archive")}
    assert group_mapping_issues([("bookings", row)]) == []
    for change in ({"tenant_id": "real-hotel"}, {"id": "not-a-reviewed-source"}, {"demo_reconstruction": {}}):
        assert len(group_mapping_issues([("bookings", {**row, **change})])) == 1


def test_financial_change_cannot_be_hidden_as_metadata_only_incident():
    entry = {"tenant_id": r.TENANT, "id": "a", "seq": 1, "prev_hash": "", "action": "payment", "after_snapshot": {"amount": 100}}
    entry["record_hash"] = audit_chain.compute_record_hash(entry, 1, "")
    entry.update(ip_address="192.0.2.1", user_agent="late", after_snapshot={"amount": 101})
    with pytest.raises(HTTPException, match="Açıklanamayan"):
        r.historical_metadata_incident([entry])


@pytest.mark.parametrize("extra", [{"confirmation": "accept all"}, {"reason": " " * 30}, {"amount": 1}, {"tenant_id": "other"}])
def test_no_arbitrary_tenant_amount_or_silent_confirmation(extra):
    base = {"request_id": str(uuid4()), "source_fingerprint": "a" * 64, "reason": "Reviewed synthetic reconstruction only", "confirmation": "RECONSTRUCT_SYNTHETIC_DEMO_100001_ONLY"}
    with pytest.raises(ValidationError):
        DemoSourceRemediationIn(**{**base, **extra})
