import pytest

from core import audit_chain
from shared_kernel import audit_helper

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


@pytest.mark.asyncio
async def test_transactional_audit_write_uses_the_hash_chain(monkeypatch):
    captured = {}

    async def fake_append(db, entry, session=None):
        captured.update({"db": db, "entry": entry, "session": session})
        return entry

    monkeypatch.setattr(audit_chain, "append_audit_log", fake_append)
    session = object()

    await audit_helper.audit_log(
        actor_id="u1",
        tenant_id="t1",
        entity_type="folio",
        entity_id="f1",
        action="folio.updated",
        session=session,
    )

    assert captured["session"] is session
    assert captured["entry"]["tenant_id"] == "t1"
    assert captured["entry"]["action"] == "folio.updated"


@pytest.mark.asyncio
async def test_financial_chain_opt_in_propagates_failure_before_any_insert(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    database = SimpleNamespace(audit_logs=SimpleNamespace(insert_one=AsyncMock()))
    monkeypatch.setattr(audit_chain, '_link_chain', AsyncMock(side_effect=RuntimeError('chain unavailable')))
    with pytest.raises(RuntimeError, match='chain unavailable'):
        await audit_chain.append_audit_log(database, {'tenant_id': 't1'}, session=object(), require_chain=True)
    database.audit_logs.insert_one.assert_not_awaited()


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("transactional", [False, True])
async def test_request_attribution_is_hashed_before_raw_or_proxy_insert(monkeypatch, wrapped, transactional):
    from copy import deepcopy
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from common.request_context import clear_request_context, set_request_context
    from core.tenant_db import AppendOnlyCollection

    session = object() if transactional else None
    recorded = []

    async def insert(document, **kwargs):
        assert kwargs.get("session") is session
        recorded.append(deepcopy(document))

    async def link(tenant_id, entry, session=None):
        assert tenant_id == "t1"
        assert entry.get("ip_address") == "203.0.113.8"
        assert entry.get("user_agent") == "audit-regression/1.0"
        return 3, "previous", audit_chain.compute_record_hash(entry, 3, "previous")

    monkeypatch.setattr(audit_chain, "_link_chain", AsyncMock(side_effect=link))
    raw = SimpleNamespace(insert_one=insert)
    database = SimpleNamespace(audit_logs=AppendOnlyCollection(raw, "audit_logs") if wrapped else raw)
    set_request_context("203.0.113.8", "audit-regression/1.0")
    try:
        await audit_chain.append_audit_log(database, {"tenant_id": "t1", "action": "check_out"}, session=session, require_chain=True)
    finally:
        clear_request_context()
    row = recorded[0]
    assert row["record_hash"] == audit_chain.compute_record_hash(row, row["seq"], row["prev_hash"])
    audit_chain._link_chain.assert_awaited_once()


async def test_presealed_record_is_not_reattributed_under_another_request(monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from common.request_context import clear_request_context, set_request_context
    from core.tenant_db import AppendOnlyCollection

    row = {"tenant_id": "t1", "action": "worker_event", "seq": 1, "prev_hash": ""}
    row["record_hash"] = audit_chain.compute_record_hash(row, 1, "")
    before = deepcopy(row)
    raw = SimpleNamespace(insert_one=AsyncMock())
    link = AsyncMock(side_effect=AssertionError("A sealed record must not reserve another sequence"))
    monkeypatch.setattr(audit_chain, "_link_chain", link)
    set_request_context("203.0.113.9", "different-request")
    try:
        await AppendOnlyCollection(raw, "audit_logs").insert_one(row)
    finally:
        clear_request_context()
    assert row == before
    assert row["record_hash"] == audit_chain.compute_record_hash(row, row["seq"], row["prev_hash"])
    link.assert_not_awaited()


@pytest.mark.parametrize("rollback", [False, True])
async def test_real_mongo_request_attribution_and_chain_commit_together(ledger_db, monkeypatch, rollback):
    from types import SimpleNamespace

    from common.request_context import clear_request_context, set_request_context
    from core.tenant_db import AppendOnlyCollection

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
