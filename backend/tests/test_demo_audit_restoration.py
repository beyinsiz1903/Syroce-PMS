"""The offline restore preserves old seals and atomically archives observations."""
from copy import deepcopy

import pytest

from core import audit_chain
from modules.pms_core import demo_source_remediation as source
from scripts import restore_demo_audit_attribution as tool

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


@pytest.fixture
async def incident_db(ledger_db, monkeypatch):
    db = ledger_db
    monkeypatch.setattr(audit_chain, "_system_db", lambda: db)
    tenant = source.TENANT
    await db.tenants.insert_one({"id": tenant, "hotel_id": "100001", "property_name": "Syroce Demo Hotel"})
    await db.tenant_settings.insert_one({"tenant_id": tenant, "business_date": "2026-10-24"})
    await db.exely_connections.insert_one({"tenant_id": tenant, "is_active": True, "hotel_code": "501694", "mode": "sandbox",
        "ari_write_enabled": False, "auto_sync_reservations": False})
    original = []
    for n in range(69):
        entry = {"id": f"row-{n}", "tenant_id": tenant, "action": "payment_recorded", "timestamp": f"2026-10-24T10:{n // 60:02d}:{n % 60:02d}Z",
            "after_snapshot": {"amount_minor": 10000, "currency": "TRY"}}
        await audit_chain.append_audit_log(db, entry, require_chain=True)
        original.append(deepcopy(entry))
    await db.audit_logs.update_many({}, {"$set": {"ip_address": "203.0.113.8", "user_agent": "late legacy attribution"}})
    # Prove coverage across retention, not just the hot collection.
    archived = await db.audit_logs.find({"seq": {"$lte": 20}}).to_list(None)
    await db.audit_logs_archive.insert_many(archived)
    await db.audit_logs.delete_many({"seq": {"$lte": 20}})
    rows = await db.audit_logs.find({}).to_list(None) + await db.audit_logs_archive.find({}).to_list(None)
    findings = source.historical_metadata_incident(rows)
    anchor = {"id": "incident", "tenant_id": tenant, "action": "demo_sources_reconstructed", "after_snapshot": {"audit_incident": findings}}
    await audit_chain.append_audit_log(db, anchor, require_chain=True)
    await db.demo_source_remediations.insert_one({"id": source.POLICY, "tenant_id": tenant,
        "plan": {"audit_incident": findings}, "audit_id": anchor["id"], "audit_hash": anchor["record_hash"]})
    return db, original


async def apply(db, plan_hash):
    return await tool.restore(db, db.client, expected_plan_hash=plan_hash,
        approval_reference="Human approval: preserve all observations and restore only the two attribution fields", actor="approved-operator")


async def test_restores_69_existing_commitments_without_resealing_and_keeps_raw_evidence(incident_db):
    db, original = incident_db
    before = await audit_chain.verify_chain(source.TENANT)
    assert len(before["breaks"]) == 69
    plan = await tool.plan(db)
    result = await apply(db, plan["plan_hash"])
    assert result["restored_count"] == 69 and not result["old_records_resealed"]
    for original_row in original:
        rows = await db.audit_logs.find({"id": original_row["id"]}).to_list(None) + await db.audit_logs_archive.find({"id": original_row["id"]}).to_list(None)
        assert len(rows) == 1
        row = rows[0]
        for field in ["record_hash", "prev_hash", "seq", "after_snapshot", "action", "timestamp"]:
            assert row[field] == original_row[field]
        assert row["ip_address"] is None and row["user_agent"] is None
    observations = await db.audit_restoration_preimages.find({}).to_list(None)
    assert len(observations) == 69
    assert all(tool.digest(row["observed_raw_record"]) == row["before_digest"] for row in observations)
    assert all(row["observed_raw_record"]["ip_address"] == "203.0.113.8" for row in observations)
    assert (await audit_chain.verify_chain(source.TENANT))["ok"]
    assert (await apply(db, plan["plan_hash"]))["replayed"]
    assert await db.audit_restoration_preimages.count_documents({}) == 69
    assert await db.audit_logs.count_documents({"action": "historical_audit_attribution_restored"}) == 1


@pytest.mark.parametrize("failure", ["changed_action", "stale_plan", "audit_insert", "changed_incident", "provider_enabled"])
async def test_any_unapproved_change_or_write_failure_preserves_all_raw_rows(incident_db, monkeypatch, failure):
    db, _ = incident_db
    plan = await tool.plan(db)
    if failure == "changed_action":
        await db.audit_logs.update_one({"id": "row-30"}, {"$set": {"action": "a different financial event"}})
    if failure == "changed_incident":
        await db.demo_source_remediations.update_one({"id": source.POLICY}, {"$set": {"plan.audit_incident.findings.0.seq": 999}})
    if failure == "provider_enabled":
        await db.exely_connections.update_one({}, {"$set": {"ari_write_enabled": True}})
    if failure == "audit_insert":
        async def fail(*_, **__):
            raise RuntimeError("injected attestation failure")
        monkeypatch.setattr(audit_chain, "append_audit_log", fail)
    with pytest.raises(Exception):
        await apply(db, "wrong" if failure == "stale_plan" else plan["plan_hash"])
    assert await db.audit_restoration_preimages.count_documents({}) == 0
    assert await db.audit_attribution_restorations.count_documents({}) == 0
    assert await db.audit_logs.count_documents({"ip_address": "203.0.113.8"}) == 49
    assert await db.audit_logs_archive.count_documents({"ip_address": "203.0.113.8"}) == 20
