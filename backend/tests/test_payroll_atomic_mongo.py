"""Real replica-set concurrency, rollback and retry tests for payroll posting."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from test_gl_sequence_index_mongo import mongo_uri  # noqa: F401

from core.tenant_db import TenantScopedDB
from domains.accounting import payroll_gl_router as pg
from shared_kernel import pos_idem

USER = SimpleNamespace(id="operator", tenant_id="qa", role="finance")


@pytest.fixture
def database(mongo_uri, monkeypatch):  # noqa: F811 - imported pytest fixture
    client = AsyncIOMotorClient(mongo_uri)
    db = client.payroll_atomic_test
    monkeypatch.setattr(pg, "db", TenantScopedDB(db, "qa"))
    monkeypatch.setattr(pg, "get_motor_database", lambda: db)
    monkeypatch.setattr(pos_idem, "_INDEXES_READY", set())
    yield db
    client.close()


async def seed(db):
    await db.gl_accounts.insert_many([
        {"tenant_id": "qa", "code": code, "name": code, "active": True, "type": kind}
        for code, kind in [("770", "expense"), ("335", "liability"), ("360", "liability")]])
    await db.payroll_gl_mapping.insert_one({"tenant_id": "qa", "wage_expense_code": "770",
        "withholding_payable_code": "360", "net_payable_code": "335"})
    await db.payroll_runs.insert_many([
        {"id": rid, "tenant_id": "qa", "status": "locked", "period_month": "2026-09",
             "parent_run_id": "parent" if rid != "parent" else None,
             "summary": {"total_gross": 325, "total_net": 232.35}} for rid in ["parent", "a", "b"]])


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [("a", "b"), ("a", "parent"), ("a", "a")])
async def test_real_parallel_posts_only_one_journal(database, ids):
    await seed(database)
    results = await asyncio.gather(*(pg.post_payroll(rid, USER) for rid in ids), return_exceptions=True)
    assert any(isinstance(r, dict) for r in results), results
    assert all(isinstance(r, dict) or isinstance(r, HTTPException) and r.status_code == 409 for r in results), results
    assert await database.gl_journal_entries.count_documents({}) == 1
    assert await database.gl_sequence_reservations.count_documents({"status": "posted"}) == 1


@pytest.mark.asyncio
async def test_real_post_failure_rolls_back_journal_and_sequence(database, monkeypatch):
    await seed(database)
    post = pg.post_journal_entry
    async def fail(*args, **kwargs):
        await post(*args, **kwargs)
        raise ConnectionError("QA interruption before commit")
    monkeypatch.setattr(pg, "post_journal_entry", fail)
    with pytest.raises(ConnectionError):
        await pg.post_payroll("a", USER)
    assert await database.gl_journal_entries.count_documents({}) == 0
    assert await database.gl_sequence_reservations.count_documents({}) == 0
    monkeypatch.setattr(pg, "post_journal_entry", post)
    result = await pg.post_payroll("a", USER)
    assert result["entry"]["posting_sequence"] == 1
    assert (await pg.post_payroll("a", USER))["entry"]["id"] == result["entry"]["id"]
