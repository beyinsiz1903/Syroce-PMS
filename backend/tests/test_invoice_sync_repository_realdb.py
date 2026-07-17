import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest

from core.integrations.errors import IntegrationConflictError
from core.integrations.invoice_sync_repository import InvoiceSyncRepository
from core.tenant_db import clear_tenant_context, set_tenant_context
from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider, InvoiceSync, InvoiceSyncState

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

@pytest.fixture(autouse=True)
def setup_tenant():
    set_tenant_context("tenant_realdb")
    yield
    clear_tenant_context()

@pytest.fixture
async def migrated_db(live_test_db):
    import bootstrap.migrations.versions.v002_invoice_sync_indexes as mig
    await mig.MIGRATION.up(live_test_db)
    yield live_test_db
    # Downgrade cleanup is handled by live_test_db destruction

async def test_repository_atomic_creation(migrated_db):
    sync_model = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id="tenant_realdb",
        invoice_id="inv1",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:hash1",
        request_uuid=str(uuid.uuid4()),
        state=InvoiceSyncState.PREPARED,
        prepared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    # First creation should succeed
    created_model, is_new = await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model)
    assert is_new is True
    assert created_model.id == sync_model.id

    # Second creation with EXACT SAME BUSINESS KEY should fetch the existing
    sync_model2 = sync_model.model_copy(update={"id": str(uuid.uuid4())})
    existing_model, is_new2 = await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model2)
    assert is_new2 is False
    assert existing_model.id == created_model.id

async def test_repository_conflict_different_business_key(migrated_db):
    req_uuid = str(uuid.uuid4())
    sync_model1 = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id="tenant_realdb",
        invoice_id="inv1",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:hash1",
        request_uuid=req_uuid,
        state=InvoiceSyncState.PREPARED,
        prepared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model1)

    # Attempt to insert a different invoice with the SAME request_uuid (violating uq_invoice_sync_provider_request_uuid)
    sync_model2 = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id="tenant_realdb",
        invoice_id="inv2",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:hash2",
        request_uuid=req_uuid,
        state=InvoiceSyncState.PREPARED,
        prepared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with pytest.raises(IntegrationConflictError) as exc:
        await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model2)
    assert "conflicting dispatch record" in str(exc.value)

async def test_repository_concurrent_transitions(migrated_db):
    sync_model = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id="tenant_realdb",
        invoice_id="inv_conc",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:hash_conc",
        request_uuid=str(uuid.uuid4()),
        state=InvoiceSyncState.PREPARED,
        prepared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    created, _ = await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model)

    async def attempt_transition(worker_id):
        return await InvoiceSyncRepository.compare_and_set_state(
            tenant_id="tenant_realdb",
            dispatch_id=created.id,
            expected_state=InvoiceSyncState.PREPARED,
            expected_version=1,
            target_state=InvoiceSyncState.QUEUED,
            update_fields={"queued_at": datetime.now(UTC)}
        )

    # Launch 5 concurrent transition attempts
    results = await asyncio.gather(*(attempt_transition(i) for i in range(5)))

    # Exactly one should succeed (return not None), others should fail (return None)
    successes = [r for r in results if r is not None]
    assert len(successes) == 1
    assert successes[0].state == InvoiceSyncState.QUEUED
    assert successes[0].version == 2
