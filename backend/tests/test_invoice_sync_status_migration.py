import uuid

import pytest
from pymongo import ASCENDING

from bootstrap.migrations.versions.v004_invoice_sync_status_index import MIGRATION

pytestmark = [pytest.mark.asyncio, pytest.mark.live_mongo]

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None

import os

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

async def _mongo_or_skip():
    if AsyncIOMotorClient is None:
        pytest.skip("motor not installed")
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=1500)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"MongoDB unreachable ({MONGO_URL})")
    return client

@pytest.fixture
async def live_test_db(monkeypatch):
    client = await _mongo_or_skip()
    db_name = f"test_mig_status_{uuid.uuid4().hex[:8]}"
    raw_db = client[db_name]

    import core.database
    from core.tenant_db import TenantAwareDBProxy

    proxy_db = TenantAwareDBProxy(raw_db)
    monkeypatch.setattr(core.database, "db", proxy_db)
    monkeypatch.setattr(core.database, "_raw_db", raw_db)

    yield raw_db

    await client.drop_database(db_name)
    client.close()

async def test_v004_migration_up_and_down(live_test_db):
    collection = live_test_db.invoice_sync

    # Run UP
    await MIGRATION.up(live_test_db)

    # Verify index created
    indexes = await collection.index_information()
    assert "ix_invoice_sync_status_poll" in indexes

    index_info = indexes["ix_invoice_sync_status_poll"]
    assert index_info["key"] == [
        ("state", ASCENDING),
        ("reconciliation_required", ASCENDING),
        ("next_status_check_at", ASCENDING),
        ("status_lease_expires_at", ASCENDING)
    ]

    # Run UP again (idempotency check)
    await MIGRATION.up(live_test_db)
    indexes_after_second_up = await collection.index_information()
    assert "ix_invoice_sync_status_poll" in indexes_after_second_up

    # Run DOWN
    await MIGRATION.down(live_test_db)
    indexes_after_down = await collection.index_information()
    assert "ix_invoice_sync_status_poll" not in indexes_after_down
