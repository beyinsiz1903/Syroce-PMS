import pytest

from core import audit_chain
from shared_kernel import audit_helper


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
