"""Real current-state queries; explicit disposable LOCAL Mongo only."""
import os
import uuid
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from test_exely_ari_return_value_dedup import change, check, scoped_change

from domains.channel_manager.ari import repositories as repo


@pytest_asyncio.fixture
async def database(monkeypatch):
    uri = os.environ.get('EXELY_INVENTORY_TEST_MONGO_URI') or os.environ.get('POS_TEST_MONGO_URI')
    assert uri and urlparse(uri).hostname in {'localhost', '127.0.0.1'}, 'Explicit LOCAL Mongo required'
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    database = client['exely_ari_dedup_test_' + uuid.uuid4().hex]
    monkeypatch.setattr(repo, 'db', database)
    await repo.ensure_current_ack_index(database)
    yield database
    await client.drop_database(database.name)
    client.close()


@pytest.mark.asyncio
async def test_real_query_allows_return_then_suppresses_only_current_value(database):
    collection = database[repo.COLL_ARI_CHANGE_SETS]
    await collection.insert_many([change(3, minute=8), change(2, minute=5)])
    assert await check(change(3)) is False
    await collection.insert_one(change(3, minute=2))
    assert await check(change(3)) is True
    indexes = await collection.index_information()
    assert indexes['ix_ari_current_cell_ack']['partialFilterExpression'] == {'status': 'acked'}


@pytest.mark.asyncio
async def test_real_foreign_tenant_ack_cannot_suppress_or_invalidate(database):
    collection = database[repo.COLL_ARI_CHANGE_SETS]
    await collection.insert_one(change(3, minute=8, tenant_id='foreign'))
    assert await check(change(3)) is False
    await collection.insert_one(change(3, minute=5))
    await collection.insert_one(change(2, minute=2, tenant_id='foreign'))
    assert await check(change(3)) is True


@pytest.mark.asyncio
async def test_real_partial_overlap_and_cross_rate_stock_change(database):
    await database[repo.COLL_ARI_CHANGE_SETS].insert_many([
        change(3, minute=8), change(2, minute=2, date_to='2026-11-10', rate_plan_code='another'),
    ])
    assert await check(change(3)) is False


@pytest.mark.asyncio
async def test_real_restriction_operation_scope_and_return(database):
    collection = database[repo.COLL_ARI_CHANGE_SETS]
    await collection.insert_many([
        scoped_change('restriction', False, operation='cta', minute=8),
        scoped_change('restriction', True, operation='ctd', minute=5),
    ])
    assert await check(scoped_change('restriction', False, operation='cta')) is True
    await collection.insert_one(scoped_change('restriction', True, operation='cta', minute=2))
    assert await check(scoped_change('restriction', False, operation='cta')) is False
