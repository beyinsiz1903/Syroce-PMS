import os
import uuid

import pytest

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None

pytestmark = [pytest.mark.asyncio, pytest.mark.live_mongo]

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

async def test_migration_v002_integration(live_test_db):
    from bootstrap.migrations.registry import discover_migrations
    from bootstrap.migrations.runner import get_migration_status, run_migrations

    # 1. discover_migrations() içinde V002 bulunuyor
    migrations = discover_migrations()
    assert any(m.version == "V002" for m in migrations)

    v002_mig = next(m for m in migrations if m.version == "V002")

    # 6. Migration checksum ve version alanları geçerli
    assert v002_mig.version == "V002"
    assert v002_mig.checksum() is not None

    # 2. run_migrations() çalışınca V002 ledger’da applied oluyor
    res1 = await run_migrations(live_test_db, migrations=[v002_mig])
    assert "V002" in res1["applied"]

    status = await get_migration_status(live_test_db)
    assert "V002" in status["applied"]

    # 4. MIGRATION.up() index’leri oluşturuyor
    indexes = await live_test_db.invoice_sync.index_information()
    assert "uq_invoice_sync_invoice_provider_kind" in indexes
    assert "uq_invoice_sync_provider_request_uuid" in indexes
    assert "uq_invoice_sync_tenant_provider_idempotency" in indexes
    assert "ix_invoice_sync_tenant_state_retry" in indexes

    # 3. İkinci çalıştırmada tekrar uygulanmıyor
    res2 = await run_migrations(live_test_db, migrations=[v002_mig])
    assert "V002" not in res2.get("applied", [])
    assert "V002" in res2.get("skipped", [])

async def test_migration_v002_rollback_on_error(live_test_db, monkeypatch):
    from bootstrap.migrations.registry import discover_migrations
    from bootstrap.migrations.runner import MigrationError, run_migrations

    migrations = discover_migrations()
    v002_mig = next(m for m in migrations if m.version == "V002")

    # 5. Hata halinde runner down() çağırıyor
    # We will mock the up() method to raise an error after it creates some indexes
    original_up = v002_mig.up

    async def failing_up(db):
        await original_up(db)
        raise RuntimeError("Simulated failure during up")

    monkeypatch.setattr(v002_mig, "up", failing_up)

    with pytest.raises(MigrationError, match="Simulated failure during up"):
        await run_migrations(live_test_db, migrations=[v002_mig])

    # Since it failed and rolled back, the indexes should NOT exist
    indexes_after = await live_test_db.invoice_sync.index_information()
    assert "uq_invoice_sync_invoice_provider_kind" not in indexes_after
    assert "uq_invoice_sync_provider_request_uuid" not in indexes_after

    from bootstrap.migrations.runner import get_migration_status
    status = await get_migration_status(live_test_db)
    assert any(f["version"] == "V002" and f["status"] == "rolled_back" for f in status["failed"])

async def test_migration_v008_integration(live_test_db):
    from bootstrap.migrations.registry import discover_migrations
    from bootstrap.migrations.runner import run_migrations

    migrations = discover_migrations()
    v008_mig = next(m for m in migrations if m.version == "V008")

    # Run V008 up
    await run_migrations(live_test_db, migrations=[v008_mig])

    indexes = await live_test_db.invoice_sync.index_information()
    assert "ix_invoice_sync_reconciliation_poll_tenant" in indexes
    assert "ix_invoice_sync_redispatch_tenant" in indexes

    # Check partialFilterExpression
    recon_idx = indexes["ix_invoice_sync_reconciliation_poll_tenant"]
    assert "partialFilterExpression" in recon_idx
    assert recon_idx["partialFilterExpression"]["state"] == "RECONCILIATION_REQUIRED"

    safe_idx = indexes["ix_invoice_sync_redispatch_tenant"]
    assert "partialFilterExpression" in safe_idx
    assert safe_idx["partialFilterExpression"]["state"] == "SAFE_TO_RETRY"

    # Run V008 down
    await v008_mig.down(live_test_db)

    indexes_after_down = await live_test_db.invoice_sync.index_information()
    assert "ix_invoice_sync_reconciliation_poll_tenant" not in indexes_after_down
    assert "ix_invoice_sync_redispatch_tenant" not in indexes_after_down
    assert "_id_" in indexes_after_down # Check older indexes are preserved

    # Run V008 up again (idempotent)
    await v008_mig.up(live_test_db)
    indexes_again = await live_test_db.invoice_sync.index_information()
    assert "ix_invoice_sync_reconciliation_poll_tenant" in indexes_again
