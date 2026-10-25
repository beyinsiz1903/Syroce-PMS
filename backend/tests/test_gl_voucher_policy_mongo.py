"""Real local Mongo checks for policy CAS, self-finalization and audit evidence."""
import asyncio
from types import SimpleNamespace

from fastapi import HTTPException

from core import audit_chain
from domains.accounting import gl_router as gl
from shared_kernel.gl_posting import verify_journal_entry_hash

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


def actor(identity="maker", role="finance", tenant="A"):
    return SimpleNamespace(id=identity, role=role, tenant_id=tenant, is_super_admin=False)


def bind(monkeypatch, db):
    monkeypatch.setattr(gl, "db", db)
    monkeypatch.setattr(gl, "_system_db", db)
    monkeypatch.setattr(audit_chain, "_system_db", lambda: db)


async def test_real_policy_concurrent_first_save_has_one_winner_and_no_cross_tenant_change(ledger_db, monkeypatch):
    bind(monkeypatch, ledger_db)
    body = gl.VoucherApprovalPolicyIn(mode="dual_control", version=0, reason="Tesis yönetiminin açık tercihi")
    results = await asyncio.gather(*(gl.save_voucher_approval_policy(body, current_user=actor(name, "admin")) for name in ["one", "two"]), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    errors = [result for result in results if isinstance(result, HTTPException)]
    assert len(errors) == 1 and errors[0].status_code == 409
    assert await ledger_db.gl_voucher_policies.count_documents({}) == 1
    assert (await gl.get_voucher_approval_policy(current_user=actor(tenant="B")))["policy"] == {"mode": "authorized_self", "version": 0}
    assert await ledger_db.audit_logs.count_documents({"tenant_id": "A", "action": "gl_voucher_policy_changed"}) == 1


async def test_real_self_finalization_seals_one_journal_and_records_reason_and_actor(ledger_db, monkeypatch):
    bind(monkeypatch, ledger_db)
    await ledger_db.gl_accounts.insert_many([
        {"tenant_id": "A", "code": "770", "name": "Sunum bütçesi", "type": "expense", "active": True},
        {"tenant_id": "A", "code": "336", "name": "Hediye kartı yükümlülüğü", "type": "liability", "active": True},
    ])
    payload = gl.VoucherCreateIn(date="2026-10-24", memo="Yapay sunum bütçesi; gerçek banka tahsilatı değil", lines=[
        gl.JournalLineIn(account_code="770", debit=200), gl.JournalLineIn(account_code="336", credit=200),
    ])
    voucher = (await gl.create_voucher(payload, current_user=actor()))["voucher"]
    reason = gl.VoucherActionIn(reason="Yapay sunum bütçesi ve belge tutarları kontrol edildi")
    first = await gl.finalize_voucher(voucher["id"], reason, current_user=actor())
    replay = await gl.finalize_voucher(voucher["id"], reason, current_user=actor())
    assert replay["already_posted"] and replay["entry"]["id"] == first["entry"]["id"]
    assert verify_journal_entry_hash(first["entry"])
    assert await ledger_db.gl_journal_entries.count_documents({}) == 1
    approval = await ledger_db.audit_logs.find_one({"tenant_id": "A", "action": "gl_voucher_approved"})
    assert approval["actor_id"] == "maker"
    assert reason.reason in approval["details"]
    assert approval["after_snapshot"]["self_approved"] is True
    assert approval["after_snapshot"]["total_debit"] == 200
    assert first["voucher"]["approval_reason"] == reason.reason
    assert (await audit_chain.verify_chain("A"))["ok"]
