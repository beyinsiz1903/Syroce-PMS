import os
import uuid

import pytest
from pymongo import ASCENDING

from bootstrap.migrations.versions.v005_incoming_invoice_lifecycle import MIGRATION

pytestmark = [pytest.mark.asyncio, pytest.mark.live_mongo]

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

async def test_v005_second_up_is_idempotent(live_test_db):
    await MIGRATION.up(live_test_db)
    # Second up should not fail and should be idempotent
    await MIGRATION.up(live_test_db)

    incoming_indexes = await live_test_db.incoming_invoices.index_information()
    assert "idx_incoming_invoices_id_unique" in incoming_indexes
    assert "idx_incoming_invoices_tenant_provider_uuid_unique" in incoming_indexes

async def test_v005_down_preserves_v004_index(live_test_db):
    # Setup v004 index explicitly if not there
    await live_test_db.invoice_sync.create_index(
        [("state", ASCENDING), ("next_poll_at", ASCENDING)],
        name="ix_invoice_sync_status_poll"
    )
    await MIGRATION.up(live_test_db)
    await MIGRATION.down(live_test_db)

    # Check v005 indexes are removed
    lifecycle_indexes_down = await live_test_db.invoice_lifecycle_actions.index_information()
    assert "idx_lifecycle_actions_tenant_idemp_key_unique" not in lifecycle_indexes_down

    # Check v004 index is preserved
    sync_indexes = await live_test_db.invoice_sync.index_information()
    assert "ix_invoice_sync_status_poll" in sync_indexes

def test_migration_loader_discovers_v005_and_v006():
    from bootstrap.migrations.registry import discover_migrations
    versions = discover_migrations()
    assert any(m.version == "V005" for m in versions), "Loader must discover V005"
    assert any(m.version == "V006" for m in versions), "Loader must discover V006"

async def test_v006_second_up_is_idempotent(live_test_db):
    from bootstrap.migrations.versions.v006_incoming_invoice_answer_atomicity import IncomingInvoiceAnswerAtomicityMigration
    migration = IncomingInvoiceAnswerAtomicityMigration()
    await migration.up(live_test_db)
    # Second up should not fail and should be idempotent
    await migration.up(live_test_db)

    indexes = await live_test_db.invoice_lifecycle_actions.index_information()
    assert "idx_lifecycle_actions_tenant_answer_guard_unique" in indexes
    guard_idx = indexes["idx_lifecycle_actions_tenant_answer_guard_unique"]
    assert guard_idx.get("unique") is True
    assert guard_idx.get("partialFilterExpression") == {"answer_guard_key": {"$type": "string"}}

async def test_v006_down_removes_index(live_test_db):
    from bootstrap.migrations.versions.v005_incoming_invoice_lifecycle import IncomingInvoiceLifecycleMigration
    await IncomingInvoiceLifecycleMigration().up(live_test_db)

    from bootstrap.migrations.versions.v006_incoming_invoice_answer_atomicity import IncomingInvoiceAnswerAtomicityMigration
    migration = IncomingInvoiceAnswerAtomicityMigration()
    await migration.up(live_test_db)
    await migration.down(live_test_db)

    indexes = await live_test_db.invoice_lifecycle_actions.index_information()
    assert "idx_lifecycle_actions_tenant_answer_guard_unique" not in indexes
    # V005 indexes must be preserved
    assert "idx_lifecycle_actions_tenant_idemp_key_unique" in indexes
