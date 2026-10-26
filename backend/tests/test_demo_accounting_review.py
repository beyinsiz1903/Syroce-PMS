import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core import audit_chain
from core.integrations import operational_gl_valuation as valuation
from core.integrations.operational_gl_bridge import DEFAULT_MAPPING
from modules.pms_core import demo_accounting_review as review
from routers.reservation_detail import DemoAccountingReviewIn
from shared_kernel.gl_posting import compute_journal_entry_hash, normalize_journal_lines

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id=review.TENANT, id="demo-operator", name="Demo Operator")


def request(preview):
    return DemoAccountingReviewIn(request_id=uuid4(), source_fingerprint=preview["source_fingerprint"],
        reason="Kullanıcı onaylı mevcut DEMO kaynak/kayıt çifti incelemesi; tarihî belge veya özgün mühür değildir.",
        confirmation="REVIEW_SYNTHETIC_DEMO_ACCOUNTING_100001_ONLY")


def sealed(bid, source, day, lines, *, source_ref=review.RUN, manifest=None):
    normalized, debit, credit = normalize_journal_lines(lines)
    entry = {"tenant_id": review.TENANT, "id": bid, "date": day, "lines": normalized, "total_debit": debit,
        "total_credit": credit, "source": source, "source_ref": source_ref, "status": "posted"}
    if manifest is not None:
        entry["source_manifest"] = manifest
    entry["entry_hash"] = compute_journal_entry_hash(entry)
    return entry


async def seed(db):
    tenant = review.TENANT
    await db.tenants.insert_one({"id": tenant, "hotel_id": "100001", "property_name": "Syroce Demo Hotel"})
    await db.tenant_settings.insert_one({"tenant_id": tenant, "business_date": "2026-10-25"})
    await db.exely_connections.insert_one({"tenant_id": tenant, "is_active": True, "hotel_code": "501694", "mode": "sandbox", "ari_write_enabled": False, "auto_sync_reservations": False})
    await db.gl_operational_mappings.insert_one({"tenant_id": tenant, **DEFAULT_MAPPING, "enabled": True})
    for bid, (day, value) in review.LEGACY.items():
        await db.gl_journal_entries.insert_one({"tenant_id": tenant, "id": bid, "date": day, "status": "posted", "source": "manual",
            "lines": [{"account_code": "100", "debit": value / 100}, {"account_code": "600", "credit": value / 100}]})
    source = {"tenant_id": tenant, "id": review.PAYMENT, "amount": 8000, "currency": "TRY", "business_date": "2026-09-05",
        "processed_at": "2026-10-15T17:17:33Z", "method": "cash", "status": "paid"}
    await db.payments.insert_one(deepcopy(source))
    prior_plan = {"documents": [{"collection": "payments", "id": review.PAYMENT, "after_hash": review.fingerprint(source)}]}
    prior_plan["source_fingerprint"] = review.fingerprint(prior_plan)
    audit = {"tenant_id": tenant, "id": "source-decision", "action": "demo_sources_reconstructed", "timestamp": "2026-10-25T10:00:00Z",
        "before_snapshot": {"source_fingerprint": prior_plan["source_fingerprint"]},
        "after_snapshot": {"document_after_hashes": [prior_plan["documents"][0]["after_hash"]]}}
    await audit_chain.append_audit_log(db, audit, require_chain=True)
    await db.demo_source_remediations.insert_one({"tenant_id": tenant, "id": review.SOURCE_POLICY, "plan": prior_plan, "audit_id": audit["id"], "audit_hash": audit["record_hash"]})
    mapping = {**DEFAULT_MAPPING, "enabled": True}
    manifest = valuation.build_plan([], [], mapping, valuation.normalized_valuation("2026-10-15",
        {"business_date": "2026-10-15", "base_currency": "TRY", "reference": "Original explicit demo day", "rates_to_try": {}}))["manifest"]
    original = sealed(review.ORIGINAL, "night_audit", "2026-10-15", [{"account_code": "100", "debit": 8000}, {"account_code": "120", "credit": 8000}])
    original["idempotency_key"] = "operational-daily:2026-10-15"
    original["entry_hash"] = compute_journal_entry_hash(original)
    contra = sealed(review.CORRECTION, "night_audit_correction", "2026-10-15", [{"account_code": "100", "credit": 8000}, {"account_code": "120", "debit": 8000}], manifest=manifest)
    contra.update(memo="Bağlı kaynak düzeltmesi " + review.ORIGINAL + " — " + manifest["source_hash"], idempotency_key="operational-correction:" + review.RUN)
    contra["entry_hash"] = compute_journal_entry_hash(contra)
    september = sealed("september-valued", "night_audit_correction", "2026-09-05", [{"account_code": "100", "debit": 8000}, {"account_code": "120", "credit": 8000}],
        source_ref="september", manifest={"sources": [{"kind": "payment", "id": review.PAYMENT, "currency": "TRY", "amount_minor": 800000}]})
    await db.gl_journal_entries.insert_many([original, contra, september])
    await db.night_audit_runs.insert_many([
        {"tenant_id": tenant, "id": review.RUN, "business_date": "2026-10-15", "status": "completed", "gl_bridge_status": "posted", "gl_journal_entry_id": review.ORIGINAL, "gl_valued_entry_id": review.CORRECTION},
        {"tenant_id": tenant, "id": "september", "business_date": "2026-09-05", "status": "completed", "gl_valued_entry_id": "september-valued"}])


@pytest.fixture(autouse=True)
def isolated(monkeypatch, ledger_db):
    monkeypatch.setattr(audit_chain, "_system_db", lambda: ledger_db)


async def test_current_review_is_atomic_replay_safe_without_resealing_history(ledger_db, monkeypatch):
    from domains.accounting import gl_router
    db = ledger_db
    await seed(db)
    before = await db.gl_journal_entries.find({}, {"_id": 0}).to_list(None)
    p = await review.preview(db, review.TENANT)
    assert p["original_seals_created"] == p["new_journals"] == 0 and not p["historical_source_verified"]
    monkeypatch.setattr(gl_router, "db", db)
    assert not (await gl_router.operational_reconciliation("2026-10-15", SimpleNamespace(tenant_id=review.TENANT, role="admin")))["healthy"]
    data = request(p)
    results = await asyncio.gather(*[review.apply(db, db.client, USER, data) for _ in range(2)])
    assert sum(bool(r["replayed"]) for r in results) == 1
    assert (await review.verified(db, review.TENANT))["legacy_reviewed_count"] == 2
    report = await gl_router.operational_reconciliation("2026-10-15", SimpleNamespace(tenant_id=review.TENANT, role="admin"))
    assert report["healthy"] and report["folios"]["gl_total"] == report["folios"]["variance"] == 0
    assert any(w["code"] == "demo_legacy_accounting_review" and not w["historical_source_verified"] for w in report["warnings"])
    assert await db.gl_journal_entries.find({}, {"_id": 0}).to_list(None) == before
    assert await db.audit_logs.count_documents({"action": "demo_legacy_accounting_reviewed"}) == 1
    with pytest.raises(HTTPException):
        await review.apply(db, db.client, USER, data.model_copy(update={"reason": "A different approved review reason"}))
    with pytest.raises(HTTPException):
        await review.preview(db, "another-hotel")


@pytest.mark.parametrize("target", ["legacy", "payment", "prior_plan", "original", "correction", "september", "review_audit", "review_plan", "review_result", "review_payload"])
async def test_source_or_receipt_tamper_is_never_hidden_by_a_review(ledger_db, target):
    db = ledger_db
    await seed(db)
    await review.apply(db, db.client, USER, request(await review.preview(db, review.TENANT)))
    collection, query, values = {
        "legacy": ("gl_journal_entries", {"id": next(iter(review.LEGACY))}, {"memo": "changed"}),
        "payment": ("payments", {"id": review.PAYMENT}, {"amount": 8001}),
        "prior_plan": ("demo_source_remediations", {"id": review.SOURCE_POLICY}, {"plan.documents.0.after_hash": "changed"}),
        "original": ("gl_journal_entries", {"id": review.ORIGINAL}, {"entry_hash": "changed"}),
        "correction": ("gl_journal_entries", {"id": review.CORRECTION}, {"entry_hash": "changed"}),
        "september": ("gl_journal_entries", {"id": "september-valued"}, {"source_manifest.sources.0.amount_minor": 799999}),
        "review_audit": ("audit_logs", {"action": "demo_legacy_accounting_reviewed"}, {"after_snapshot.plan_hash": "changed"}),
        "review_plan": ("demo_source_remediations", {"id": review.POLICY}, {"plan.amount_minor": 799999}),
        "review_result": ("demo_source_remediations", {"id": review.POLICY}, {"result.reviewed_by": "changed"}),
        "review_payload": ("demo_source_remediations", {"id": review.POLICY}, {"payload_hash": "changed"}),
    }[target]
    await db[collection].update_one(query, {"$set": values})
    with pytest.raises(HTTPException):
        await review.verified(db, review.TENANT)


async def test_stale_preview_provider_guard_and_audit_failure_never_commit_a_receipt(ledger_db, monkeypatch):
    db = ledger_db
    await seed(db)
    data = request(await review.preview(db, review.TENANT))
    await db.exely_connections.update_one({}, {"$set": {"ari_write_enabled": True}})
    with pytest.raises(HTTPException):
        await review.apply(db, db.client, USER, data)
    await db.exely_connections.update_one({}, {"$set": {"ari_write_enabled": False}})
    with pytest.raises(HTTPException):
        await review.apply(db, db.client, USER, data.model_copy(update={"source_fingerprint": "0" * 64}))
    monkeypatch.setattr(review, "append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await review.apply(db, db.client, USER, data)
    assert not await db.demo_source_remediations.find_one({"id": review.POLICY})


@pytest.mark.parametrize("missing", ["sequence", "documents", "document_hash"])
async def test_incomplete_parent_proof_fails_with_review_conflict_not_key_error(ledger_db, missing):
    await seed(ledger_db)
    collection, query, field = {
        "sequence": ("audit_logs", {"id": "source-decision"}, "seq"),
        "documents": ("demo_source_remediations", {"id": review.SOURCE_POLICY}, "plan.documents"),
        "document_hash": ("demo_source_remediations", {"id": review.SOURCE_POLICY}, "plan.documents.0.after_hash"),
    }[missing]
    await ledger_db[collection].update_one(query, {"$unset": {field: ""}})
    with pytest.raises(HTTPException) as error:
        await review.preview(ledger_db, review.TENANT)
    assert error.value.status_code == 409


def test_review_payload_is_fixed_scope_and_requires_explicit_confirmation():
    p = {"source_fingerprint": "0" * 64}
    data = request(p)
    with pytest.raises(ValidationError):
        DemoAccountingReviewIn(**{**data.model_dump(), "tenant_id": "another"})
    with pytest.raises(ValidationError):
        DemoAccountingReviewIn(**{**data.model_dump(), "confirmation": "anything"})
