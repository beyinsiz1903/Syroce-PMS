"""Real isolated replica-set acceptance; no production database is permitted."""
from types import SimpleNamespace

import pytest

from common.request_context import clear_request_context, set_request_context
from core import audit_chain
from core.tenant_db import AppendOnlyCollection

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


@pytest.mark.parametrize("rollback", [False, True])
async def test_real_mongo_request_attribution_and_chain_commit_together(ledger_db, monkeypatch, rollback):
    monkeypatch.setattr(audit_chain, "_system_db", lambda: ledger_db)
    guarded = SimpleNamespace(audit_logs=AppendOnlyCollection(ledger_db.audit_logs, "audit_logs"))
    set_request_context("203.0.113.8", "transactional-audit/1.0")
    try:
        async with await ledger_db.client.start_session() as session:
            session.start_transaction()
            await audit_chain.append_audit_log(guarded,
                {"tenant_id": "t1", "action": "folio_window_opened", "after_snapshot": {"folio_id": "f1"}},
                session=session, require_chain=True)
            if rollback:
                await session.abort_transaction()
            else:
                await session.commit_transaction()
    finally:
        clear_request_context()
    if rollback:
        assert await ledger_db.audit_logs.count_documents({}) == 0
        assert await ledger_db.audit_chain_state.count_documents({}) == 0
    else:
        row = await ledger_db.audit_logs.find_one({"tenant_id": "t1"})
        assert row["ip_address"] == "203.0.113.8" and row["user_agent"] == "transactional-audit/1.0"
        assert row["record_hash"] == audit_chain.compute_record_hash(row, row["seq"], row["prev_hash"])
        state = await ledger_db.audit_chain_state.find_one({"_id": "t1"})
        assert state["seq"] == row["seq"] == 1 and state["last_hash"] == row["record_hash"]
