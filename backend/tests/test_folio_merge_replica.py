"""In-card folio merges: real local transactions, rollback and concurrent replay."""
import asyncio
import os
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse
from uuid import uuid4

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from domains.pms import folio_window_router as routes
from tests.unit.test_folio_merge import ledger, request  # noqa: F401


@pytest_asyncio.fixture
async def stored(ledger, monkeypatch):
    uri = os.getenv('POS_TEST_MONGO_URI')
    assert uri and urlparse(uri).hostname in {'localhost', '127.0.0.1'}, 'Explicit LOCAL replica required'
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    database = client['folio_merge_acceptance_' + uuid4().hex]
    assert (await client.admin.command('hello')).get('setName'), 'Transactions require a replica set'
    try:
        for name, collection in vars(ledger).items():
            await database.create_collection(name)
            if collection.rows:
                await database[name].insert_many(deepcopy(collection.rows))
        await database.reservation_financial_locks.create_index(
            [('tenant_id', 1), ('kind', 1), ('resource_id', 1)], unique=True)
        monkeypatch.setattr(routes, 'db', database)
        monkeypatch.setattr('core.database.client', client)
        monkeypatch.setattr('core.report_cache.invalidate_financial_report_caches', lambda *_: None)
        yield database
    finally:
        assert database.name.startswith('folio_merge_acceptance_')
        await client.drop_database(database.name)
        client.close()


async def merge(body):
    return await routes.merge_windows(body, SimpleNamespace(id='operator', tenant_id='hotel-a'), None)


@pytest.mark.asyncio
async def test_concurrent_same_merge_commits_one_movement_and_preserves_source_ids(stored, ledger):
    body = await request(ledger)
    results = await asyncio.gather(merge(body), merge(body))
    assert sum(not r['replayed'] for r in results) == 1
    assert await stored.folio_operations.count_documents({}) == 1
    assert await stored.pms_audit_trail.count_documents({}) == 1
    for name in ('folio_charges', 'payments', 'extra_charges', 'folio_postings', 'deposits'):
        rows = await stored[name].find({}, {'_id': 0}).to_list(None)
        assert sorted(rows, key=lambda r: r['id']) == sorted(
            [{**r, 'folio_id': 'target'} for r in ledger[name].rows], key=lambda r: r['id'])
    assert (await stored.folios.find_one({'id': 'source'}))['balance'] == 0
    assert (await stored.folios.find_one({'id': 'target'}))['balance'] == results[0]['target_balance']


@pytest.mark.asyncio
async def test_failure_after_moving_money_rolls_back_all_rows(stored, ledger, monkeypatch):
    import modules.pms_core.folio_merge as service

    snapshots = service.folio_snapshots
    calls = 0

    async def fail_second_read(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('Injected failure after source was closed')
        return await snapshots(*args, **kwargs)

    monkeypatch.setattr(service, 'folio_snapshots', fail_second_read)
    with pytest.raises(RuntimeError, match='after source was closed'):
        await merge(await request(ledger))
    for name, collection in vars(ledger).items():
        rows = await stored[name].find({}, {'_id': 0}).to_list(None)
        assert rows == collection.rows, name
    assert not await stored.reservation_financial_locks.count_documents({})


@pytest.mark.asyncio
async def test_audit_insert_failure_rolls_back_movement_and_idempotency_record(stored, ledger, monkeypatch):
    original_insert = type(stored.pms_audit_trail).insert_one

    async def insert(collection, *args, **kwargs):
        if collection.name == 'pms_audit_trail':
            raise RuntimeError('Audit unavailable')
        return await original_insert(collection, *args, **kwargs)

    monkeypatch.setattr(type(stored.pms_audit_trail), 'insert_one', insert)
    with pytest.raises(RuntimeError, match='Audit unavailable'):
        await merge(await request(ledger))
    assert not await stored.folio_operations.count_documents({})
    assert (await stored.folios.find_one({'id': 'source'}))['status'] == 'open'
    assert await stored.folio_charges.count_documents({'folio_id': 'target'}) == 0


@pytest.mark.asyncio
async def test_missing_transaction_support_fails_without_changing_money(stored, ledger, monkeypatch):
    from fastapi import HTTPException
    from pymongo.errors import OperationFailure

    monkeypatch.setattr('core.booking_atomicity.with_resource_locks', AsyncMock(
        side_effect=OperationFailure('Transaction numbers are only allowed on a replica set', code=20)))
    with pytest.raises(HTTPException) as error:
        await merge(await request(ledger))
    assert error.value.status_code == 503
    assert not await stored.folio_operations.count_documents({})
    assert (await stored.folios.find_one({'id': 'source'}))['status'] == 'open'
