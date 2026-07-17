import os
import uuid
from datetime import UTC, datetime

import pytest

from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
from core.tenant_db import clear_tenant_context, set_tenant_context
from models.schemas.invoice_lifecycle import (
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
    InvoiceLifecycleDirection,
)

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
    db_name = f"test_lifecycle_{uuid.uuid4().hex[:8]}"
    raw_db = client[db_name]

    import core.database
    from core.tenant_db import TenantAwareDBProxy

    proxy_db = TenantAwareDBProxy(raw_db)
    monkeypatch.setattr(core.database, "db", proxy_db)
    monkeypatch.setattr(core.database, "_raw_db", raw_db)

    yield raw_db

    await client.drop_database(db_name)
    client.close()

@pytest.fixture(autouse=True)
def setup_tenant():
    set_tenant_context("tenant_realdb")
    yield
    clear_tenant_context()

@pytest.fixture
async def migrated_db(live_test_db):
    import bootstrap.migrations.versions.v005_incoming_invoice_lifecycle as mig5
    await mig5.MIGRATION.up(live_test_db)
    yield live_test_db

async def test_repo_tenant_isolation(migrated_db):
    tenant_1 = "tenant_1"
    tenant_2 = "tenant_2"
    action_id = str(uuid.uuid4())
    
    action = InvoiceLifecycleAction(
        id=action_id,
        tenant_id=tenant_1,
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="inv_1",
        source_provider_uuid="uuid-1",
        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid="req-1",
        idempotency_key=f"{tenant_1}:inv_1:ACCEPT:req-1",
        request_fingerprint="fingerprint-1",
        requested_by="admin",
        requested_at=datetime.now(UTC)
    )
    
    await InvoiceLifecycleRepository.create_action(action)
    
    # tenant 1 sees it
    assert await InvoiceLifecycleRepository.get_by_id(tenant_1, action_id) is not None
    # tenant 2 does not see it
    assert await InvoiceLifecycleRepository.get_by_id(tenant_2, action_id) is None
    
    # test lease isolation
    claimed_t2 = await InvoiceLifecycleRepository.claim_action_lease(tenant_2, action_id, "worker", 60)
    assert claimed_t2 is None
    
    claimed_t1 = await InvoiceLifecycleRepository.claim_action_lease(tenant_1, action_id, "worker", 60)
    assert claimed_t1 is not None
    assert claimed_t1.id == action_id
    
    # cross-tenant update should fail
    updated_t2 = await InvoiceLifecycleRepository.update_action_result(tenant_2, action_id, "worker", {"state": InvoiceLifecycleActionState.SUCCEEDED.value})
    assert not updated_t2
    
    # correct tenant update should succeed
    updated_t1 = await InvoiceLifecycleRepository.update_action_result(tenant_1, action_id, "worker", {"state": InvoiceLifecycleActionState.SUCCEEDED.value})
    assert updated_t1

async def test_repo_concurrent_workers_and_stale_lease(migrated_db):
    tenant_id = "tenant_1"
    action_id = str(uuid.uuid4())
    
    action = InvoiceLifecycleAction(
        id=action_id,
        tenant_id=tenant_id,
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="inv_2",
        source_provider_uuid="uuid-2",
        action_type=InvoiceLifecycleActionType.ACCEPT_INCOMING,
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid="req-2",
        idempotency_key=f"{tenant_id}:inv_2:ACCEPT:req-2",
        request_fingerprint="fingerprint-2",
        requested_by="admin",
        requested_at=datetime.now(UTC)
    )
    await InvoiceLifecycleRepository.create_action(action)
    
    # Worker 1 claims it
    w1_lease = await InvoiceLifecycleRepository.claim_action_lease(tenant_id, action_id, "worker_1", 1) # 1 second lease
    assert w1_lease is not None
    
    # Worker 2 tries to claim it concurrently
    w2_lease = await InvoiceLifecycleRepository.claim_action_lease(tenant_id, action_id, "worker_2", 60)
    assert w2_lease is None # Cannot claim!
    
    import asyncio
    await asyncio.sleep(1.5) # Wait for lease to become stale
    
    # Worker 2 tries again -> stale lease recovery
    w2_lease_recovered = await InvoiceLifecycleRepository.claim_action_lease(tenant_id, action_id, "worker_2", 60)
    assert w2_lease_recovered is not None
    assert w2_lease_recovered.lifecycle_lease_owner == "worker_2"
