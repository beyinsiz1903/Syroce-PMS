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
    db_name = f"test_sync_v003_{uuid.uuid4().hex[:8]}"
    raw_db = client[db_name]

    import core.database
    from core.tenant_db import TenantAwareDBProxy

    proxy_db = TenantAwareDBProxy(raw_db)
    monkeypatch.setattr(core.database, "db", proxy_db)
    monkeypatch.setattr(core.database, "_raw_db", raw_db)

    yield raw_db

    await client.drop_database(db_name)
    client.close()

async def test_migration_v003_integration(live_test_db):
    from bootstrap.migrations.registry import discover_migrations
    from bootstrap.migrations.runner import get_migration_status, run_migrations

    migrations = discover_migrations()
    v002_mig = next(m for m in migrations if m.version == "V002")
    v003_mig = next(m for m in migrations if m.version == "V003")

    # Run V002 first
    await run_migrations(live_test_db, migrations=[v002_mig])

    # 1. run_migrations() applied V003
    res1 = await run_migrations(live_test_db, migrations=[v003_mig])
    assert "V003" in res1["applied"]

    status = await get_migration_status(live_test_db)
    assert "V003" in status["applied"]

    # 2. Index created
    indexes = await live_test_db.invoice_sync.index_information()
    assert "ix_invoice_sync_worker_poll" in indexes

    # 3. Second run skips
    res2 = await run_migrations(live_test_db, migrations=[v003_mig])
    assert "V003" not in res2.get("applied", [])
    assert "V003" in res2.get("skipped", [])

    # Test down logic
    await v003_mig.down(live_test_db)
    indexes_after_down = await live_test_db.invoice_sync.index_information()
    assert "ix_invoice_sync_worker_poll" not in indexes_after_down

async def test_migration_v003_rollback_on_error(live_test_db, monkeypatch):
    from bootstrap.migrations.registry import discover_migrations
    from bootstrap.migrations.runner import MigrationError, run_migrations

    migrations = discover_migrations()
    v003_mig = next(m for m in migrations if m.version == "V003")

    original_up = v003_mig.up

    async def failing_up(db):
        await original_up(db)
        raise RuntimeError("Simulated failure during V003 up")

    monkeypatch.setattr(v003_mig, "up", failing_up)

    with pytest.raises(MigrationError, match="Simulated failure during V003 up"):
        await run_migrations(live_test_db, migrations=[v003_mig])

    indexes_after = await live_test_db.invoice_sync.index_information()
    assert "ix_invoice_sync_worker_poll" not in indexes_after

    from bootstrap.migrations.runner import get_migration_status
    status = await get_migration_status(live_test_db)
    assert any(f["version"] == "V003" and f["status"] == "rolled_back" for f in status["failed"])
