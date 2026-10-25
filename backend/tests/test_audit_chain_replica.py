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


async def test_real_mongo_append_during_verification_is_not_a_false_tail_deletion(ledger_db, monkeypatch):
    monkeypatch.setattr(audit_chain, '_system_db', lambda: ledger_db)
    for n in range(2):
        await audit_chain.append_audit_log(ledger_db, {'id': str(n), 'tenant_id': 't1', 'action': 'source_committed',
            'timestamp': f'2026-10-25T14:00:0{n}Z'})
    original = await ledger_db.audit_logs.find({}).sort('seq', 1).to_list(None)

    class AppendAfterCapturedState:
        def __init__(self):
            self.injected = False
        def __getattr__(self, name):
            return getattr(ledger_db.audit_chain_state, name)
        async def find_one(self, *args, **kwargs):
            state = await ledger_db.audit_chain_state.find_one(*args, **kwargs)
            if not self.injected:
                self.injected = True
                await audit_chain.append_audit_log(ledger_db, {'id': 'concurrent', 'tenant_id': 't1',
                    'action': 'another_request', 'timestamp': '2026-10-25T14:00:03Z'})
            return state
    state = AppendAfterCapturedState()
    class DatabaseView:
        def __getitem__(self, name):
            return state if name == 'audit_chain_state' else ledger_db[name]
    monkeypatch.setattr(audit_chain, '_system_db', DatabaseView)
    result = await audit_chain.verify_chain('t1')
    assert result['ok'] and result['breaks'] == []
    assert result['as_of_seq'] == result['last_seq'] == 2
    assert result['observed_latest_seq'] == 3 and result['concurrent_appends']
    assert await ledger_db.audit_logs.find({'seq': {'$lte': 2}}).sort('seq', 1).to_list(None) == original
    # The next independent scan verifies the appended event as well.
    monkeypatch.setattr(audit_chain, '_system_db', lambda: ledger_db)
    assert (await audit_chain.verify_chain('t1'))['checked'] == 3


async def test_real_mongo_deleted_tail_and_changed_content_still_fail(ledger_db, monkeypatch):
    monkeypatch.setattr(audit_chain, '_system_db', lambda: ledger_db)
    for n in range(3):
        await audit_chain.append_audit_log(ledger_db, {'id': str(n), 'tenant_id': 't1', 'action': 'source_committed',
            'timestamp': f'2026-10-25T14:00:0{n}Z'})
    # Only this randomly-named isolated test database is mutated to prove detection.
    await ledger_db.audit_logs.delete_one({'seq': 3})
    await ledger_db.audit_logs.update_one({'seq': 1}, {'$set': {'action': 'changed'}})
    result = await audit_chain.verify_chain('t1')
    assert not result['ok']
    assert {row['reason'] for row in result['breaks']} >= {'content_hash_mismatch', 'chain_state_tip_mismatch'}


async def test_real_mongo_append_after_both_cursors_before_tip_read_matches_live_race(ledger_db, monkeypatch):
    monkeypatch.setattr(audit_chain, '_system_db', lambda: ledger_db)
    for n in range(2):
        await audit_chain.append_audit_log(ledger_db, {'id': str(n), 'tenant_id': 't1', 'action': 'source_committed'})
    class ArchiveCursor:
        def __init__(self, cursor):
            self.cursor = cursor
        def sort(self, *args):
            self.cursor = self.cursor.sort(*args)
            return self
        def limit(self, *args):
            self.cursor = self.cursor.limit(*args)
            return self
        async def to_list(self, length):
            result = await self.cursor.to_list(length)
            # Precisely the observed race: rows consumed, another request
            # commits, then the verifier reads the live state tip.
            await audit_chain.append_audit_log(ledger_db, {'id': 'new', 'tenant_id': 't1', 'action': 'concurrent'})
            return result
    archive = SimpleNamespace(find=lambda *args: ArchiveCursor(ledger_db.audit_logs_archive.find(*args)))
    archive.count_documents = ledger_db.audit_logs_archive.count_documents
    class DatabaseView:
        def __getitem__(self, name):
            return archive if name == 'audit_logs_archive' else ledger_db[name]
    monkeypatch.setattr(audit_chain, '_system_db', DatabaseView)
    result = await audit_chain.verify_chain('t1')
    assert result['ok'] and result['breaks'] == []
    assert result['checked'] == result['as_of_seq'] == 2 and result['observed_latest_seq'] == 3
    assert result['concurrent_appends']


async def test_real_mongo_limited_scan_discloses_its_incomplete_prefix(ledger_db, monkeypatch):
    monkeypatch.setattr(audit_chain, '_system_db', lambda: ledger_db)
    for n in range(3):
        await audit_chain.append_audit_log(ledger_db, {'id': str(n), 'tenant_id': 't1', 'action': 'source_committed'})
    result = await audit_chain.verify_chain('t1', limit=1)
    assert result['truncated'] and result['checked'] == result['last_seq'] == 1
    assert result['as_of_seq'] == 3 and result['breaks'] == []
