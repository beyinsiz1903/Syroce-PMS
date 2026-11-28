"""Explicit synthetic classification preserves zero postings and source history."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from core import audit_chain
from modules.pms_core import demo_comp_reconstruction as repair

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


@pytest.fixture(autouse=True)
def isolated_audit_state(ledger_db, monkeypatch):
    monkeypatch.setattr(audit_chain, "_system_db", lambda: ledger_db)


async def seed(db):
    await db.tenants.insert_one({"id": repair.TENANT, "hotel_id": "100001", "property_name": "Syroce Demo Hotel"})
    await db.exely_connections.insert_one({"tenant_id": repair.TENANT, "is_active": True, "hotel_code": "501694", "mode": "sandbox"})
    await db.tenant_settings.insert_one({"tenant_id": repair.TENANT, "business_date": "2026-11-14"})
    await db.night_audit_runs.insert_one({"id": "night12", "tenant_id": repair.TENANT, "business_date": "2026-11-12", "status": "completed", "gl_bridge_status": "posted", "gl_valued_entry_id": "old-sealed"})
    for collection, source_id, gross in repair.SOURCES:
        await db[collection].insert_one({"id": source_id, "tenant_id": repair.TENANT,
            "business_date": "2026-11-12", "currency": "TRY", "total": 0, "amount": 0,
            "is_complimentary": True, "complimentary_original_amount": gross, "vat_amount": 0, "tax_amount": 0})


def request(plan, reason="Kullanıcı onaylı yeni sentetik test tanımı, özgün vergi doğrulanmadı."):
    return SimpleNamespace(request_id=uuid4(), source_fingerprint=plan["source_fingerprint"], reason=reason)


@pytest.mark.asyncio
async def test_preview_is_readonly_and_names_the_new_assumption(ledger_db):
    await seed(ledger_db)
    plan = await repair.preview(ledger_db, repair.TENANT)
    assert plan["historical_source_verified"] is False
    assert plan["vat_rate"] == 20 and plan["tax_inclusive"] is True
    assert [x["snapshot"]["net_amount"] for x in plan["documents"]] == [20.83, 50]
    assert await ledger_db.demo_comp_reconstructions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_apply_retains_before_images_and_all_posted_values_and_replays_once(ledger_db):
    await seed(ledger_db)
    before = [await ledger_db[c].find_one({"id": i}, {"_id": 0}) for c, i, _ in repair.SOURCES]
    plan = await repair.preview(ledger_db, repair.TENANT)
    user = SimpleNamespace(id="operator", tenant_id=repair.TENANT, name="Operator")
    data = request(plan)
    result = await repair.apply(ledger_db, ledger_db.client, user, data)
    again = await repair.apply(ledger_db, ledger_db.client, user, data)
    assert result["applied"] and again["replayed"]
    receipt = await ledger_db.demo_comp_reconstructions.find_one({"id": repair.POLICY})
    assert receipt["before"] == before
    assert receipt["night_audit_before"]["gl_bridge_status"] == "posted"
    run = await ledger_db.night_audit_runs.find_one({"id": "night12"})
    assert run["gl_bridge_status"] == "valuation_required"
    assert run["gl_valued_entry_id"] == "old-sealed"
    for (collection, source_id, _), original in zip(repair.SOURCES, before, strict=True):
        after = await ledger_db[collection].find_one({"id": source_id}, {"_id": 0})
        for key, value in original.items():
            assert after[key] == value
        assert after["demo_reconstruction"]["historical_source_verified"] is False
    assert await ledger_db.demo_comp_reconstructions.count_documents({}) == 1
    assert await ledger_db.payments.count_documents({}) == 0
    assert await ledger_db.gl_journal_entries.count_documents({}) == 0
    assert await ledger_db.outbox_events.count_documents({}) == 0
    with pytest.raises(HTTPException) as error:
        await repair.apply(ledger_db, ledger_db.client, user, request(plan, reason="Farklı bir sentetik düzeltme gerekçesi."))
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", [{"total": 1}, {"currency": "USD"}, {"voided": True},
    {"complimentary_original_amount": 26}, {"complimentary_original_tax_snapshot": {"net_amount": 25}}])
async def test_changed_or_already_classified_sources_fail_closed(ledger_db, mutation):
    await seed(ledger_db)
    collection, source_id, _ = repair.SOURCES[0]
    await ledger_db[collection].update_one({"id": source_id}, {"$set": deepcopy(mutation)})
    with pytest.raises(HTTPException):
        await repair.preview(ledger_db, repair.TENANT)
    assert await ledger_db.demo_comp_reconstructions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_stale_preview_and_foreign_tenant_never_write(ledger_db):
    await seed(ledger_db)
    plan = await repair.preview(ledger_db, repair.TENANT)
    collection, source_id, _ = repair.SOURCES[1]
    await ledger_db[collection].update_one({"id": source_id}, {"$set": {"description": "changed"}})
    with pytest.raises(HTTPException):
        await repair.apply(ledger_db, ledger_db.client, SimpleNamespace(id="o", name="O", tenant_id=repair.TENANT), request(plan))
    with pytest.raises(HTTPException):
        await repair.preview(ledger_db, "other")
    assert await ledger_db.demo_comp_reconstructions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_both_sources_and_receipt(ledger_db, monkeypatch):
    await seed(ledger_db)
    plan = await repair.preview(ledger_db, repair.TENANT)
    async def fail(*args, **kwargs):
        raise RuntimeError("sealed audit unavailable")
    monkeypatch.setattr(repair, "append_audit_log", fail)
    with pytest.raises(RuntimeError):
        await repair.apply(ledger_db, ledger_db.client, SimpleNamespace(id="o", name="O", tenant_id=repair.TENANT), request(plan))
    for collection, source_id, _ in repair.SOURCES:
        row = await ledger_db[collection].find_one({"id": source_id}, {"_id": 0})
        assert "demo_reconstruction" not in row
        assert "complimentary_original_tax_snapshot" not in row
    assert await ledger_db.demo_comp_reconstructions.count_documents({}) == 0
    assert (await ledger_db.night_audit_runs.find_one({"id": "night12"}))["gl_bridge_status"] == "posted"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["before", "result", "source", "audit"])
async def test_tampering_never_returns_a_successful_receipt(ledger_db, target):
    await seed(ledger_db)
    plan = await repair.preview(ledger_db, repair.TENANT)
    await repair.apply(ledger_db, ledger_db.client, SimpleNamespace(id="o", name="O", tenant_id=repair.TENANT), request(plan))
    if target in {"before", "result"}:
        key = "before.0.total" if target == "before" else "result.posted_amount_change"
        await ledger_db.demo_comp_reconstructions.update_one({"id": repair.POLICY}, {"$set": {key: 99}})
    elif target == "source":
        await ledger_db.folio_charges.update_one({"id": repair.SOURCES[0][1]}, {"$set": {"total": 99}})
    else:
        await ledger_db.audit_logs.update_one({"entity_id": repair.POLICY}, {"$set": {"action": "changed"}})
    with pytest.raises(HTTPException):
        await repair.preview(ledger_db, repair.TENANT)


@pytest.mark.asyncio
async def test_report_and_excel_disclose_new_assumption_without_creating_revenue(ledger_db, monkeypatch):
    from io import BytesIO

    from openpyxl import load_workbook

    from routers.finance import folio

    await seed(ledger_db)
    plan = await repair.preview(ledger_db, repair.TENANT)
    user = SimpleNamespace(id="o", name="O", tenant_id=repair.TENANT)
    await repair.apply(ledger_db, ledger_db.client, user, request(plan))
    monkeypatch.setattr(folio, "db", ledger_db)
    day = "2026-11-12"
    report = await folio.revenue_by_category.__wrapped__(day, day, user, None)
    totals = report["totals_by_currency"]["TRY"]
    assert totals["total"] == totals["net"] == totals["vat"] == 0
    assert totals["subtotal"] == totals["discount"] == 70.83
    reconciliation = report["reconciliation"]
    assert reconciliation["concession_unknown_count"] == 0
    assert len(reconciliation["demo_comp_definition_sources"]) == 2
    assert all(not s["historical_source_verified"] for s in reconciliation["demo_comp_definition_sources"])
    output = await folio.revenue_by_category_excel(day, day, report["snapshot"], user, None)
    book = load_workbook(BytesIO(b"".join([part async for part in output.body_iterator])), data_only=True)
    sheet = book["Sentetik Test Düzeltmeleri"]
    text = str(list(sheet.values))
    assert "özgün tarihî vergi doğrulanmadı" in text
    assert all(source_id in text for _, source_id, _ in repair.SOURCES)


@pytest.mark.asyncio
async def test_route_refuses_low_privilege_before_any_source_read(monkeypatch):
    from routers import reservation_detail as routes
    for endpoint in (routes.preview_demo_comp_reconstruction, routes.apply_demo_comp_reconstruction):
        user = SimpleNamespace(role="housekeeping", tenant_id=repair.TENANT)
        with pytest.raises(HTTPException) as error:
            if endpoint == routes.apply_demo_comp_reconstruction:
                await endpoint(SimpleNamespace(), current_user=user)
            else:
                await endpoint(current_user=user)
        assert error.value.status_code == 403


def test_input_requires_exact_scope_confirmation_and_meaningful_reason():
    from pydantic import ValidationError

    from routers.reservation_detail import DemoCompReconstructionIn
    body = {"request_id": str(uuid4()), "source_fingerprint": "a" * 64,
            "reason": "Kullanıcı onaylı sentetik test tanımı", "confirmation": "DEFINE_SYNTHETIC_COMP_25_60_ONLY"}
    assert DemoCompReconstructionIn(**body).reason == body["reason"]
    for change in ({"confirmation": "OTHER"}, {"reason": " " * 25}, {"tenant_id": "other"}, {"source_fingerprint": "x"}):
        with pytest.raises(ValidationError):
            DemoCompReconstructionIn(**{**body, **change})
