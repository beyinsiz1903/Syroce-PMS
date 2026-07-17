import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.live_mongo]

import uuid
import os
try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None

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
    db_name = f"test_sync_{uuid.uuid4().hex[:8]}"
    raw_db = client[db_name]
    
    import core.database
    from core.tenant_db import TenantAwareDBProxy
    
    proxy_db = TenantAwareDBProxy(raw_db)
    monkeypatch.setattr(core.database, "db", proxy_db)
    monkeypatch.setattr(core.database, "_raw_db", raw_db)
    
    yield raw_db
    
    await client.drop_database(db_name)
    client.close()

async def test_migration_v002_up_and_down(live_test_db):
    import bootstrap.migrations.versions.v002_invoice_sync_indexes as mig
    
    # Run upgrade
    await mig.upgrade(live_test_db)
    
    # Verify indexes
    indexes = await live_test_db.invoice_sync.index_information()
    assert "uq_invoice_sync_invoice_provider_kind" in indexes
    assert "uq_invoice_sync_provider_request_uuid" in indexes
    assert "uq_invoice_sync_tenant_provider_idempotency" in indexes
    assert "ix_invoice_sync_tenant_state_retry" in indexes
    
    # Verify uniqueness constraint actually blocks duplicates
    await live_test_db.invoice_sync.insert_one({
        "tenant_id": "t1",
        "invoice_id": "inv1",
        "provider": "NILVERA",
        "document_kind": "E_INVOICE",
        "idempotency_key": "key1",
        "request_uuid": "uuid1"
    })
    
    from pymongo.errors import DuplicateKeyError
    
    with pytest.raises(DuplicateKeyError):
        # same business key
        await live_test_db.invoice_sync.insert_one({
            "tenant_id": "t1",
            "invoice_id": "inv1",
            "provider": "NILVERA",
            "document_kind": "E_INVOICE",
            "idempotency_key": "key2",
            "request_uuid": "uuid2"
        })
        
    with pytest.raises(DuplicateKeyError):
        # same uuid
        await live_test_db.invoice_sync.insert_one({
            "tenant_id": "t2",
            "invoice_id": "inv2",
            "provider": "NILVERA",
            "document_kind": "E_ARCHIVE",
            "idempotency_key": "key3",
            "request_uuid": "uuid1" # collision
        })

    # Run downgrade
    await mig.downgrade(live_test_db)
    indexes_after_down = await live_test_db.invoice_sync.index_information()
    assert "uq_invoice_sync_invoice_provider_kind" not in indexes_after_down
