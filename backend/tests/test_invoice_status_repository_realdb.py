import uuid
from datetime import UTC, datetime, timedelta

import pytest

from core.integrations.invoice_status_repository import InvoiceStatusRepository
from core.integrations.invoice_sync_repository import InvoiceSyncRepository
from core.tenant_db import clear_tenant_context, set_tenant_context
from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider, InvoiceSync, InvoiceSyncState

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
    db_name = f"test_status_{uuid.uuid4().hex[:8]}"
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
    import bootstrap.migrations.versions.v002_invoice_sync_indexes as mig2
    import bootstrap.migrations.versions.v003_invoice_sync_worker_index as mig3
    import bootstrap.migrations.versions.v004_invoice_sync_status_index as mig4
    await mig2.MIGRATION.up(live_test_db)
    await mig3.MIGRATION.up(live_test_db)
    await mig4.MIGRATION.up(live_test_db)
    yield live_test_db

async def test_claim_status_lease(migrated_db):
    sync_model = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id="tenant_realdb",
        invoice_id="inv_status_1",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:status_1",
        request_uuid=str(uuid.uuid4()),
        state=InvoiceSyncState.SUBMITTED,
        prepared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        next_status_check_at=datetime.now(UTC),
    )
    await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model)

    # Claim lease
    claimed = await InvoiceStatusRepository.claim_status_lease(
        tenant_id="tenant_realdb",
        dispatch_id=sync_model.id,
        worker_id="worker_1",
        lease_duration_sec=60
    )
    assert claimed is not None
    assert claimed.status_lease_owner == "worker_1"

    # Concurrent claim should fail
    claimed_again = await InvoiceStatusRepository.claim_status_lease(
        tenant_id="tenant_realdb",
        dispatch_id=sync_model.id,
        worker_id="worker_2",
        lease_duration_sec=60
    )
    assert claimed_again is None

async def test_claim_status_lease_expired(migrated_db):
    sync_model = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id="tenant_realdb",
        invoice_id="inv_status_2",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:status_2",
        request_uuid=str(uuid.uuid4()),
        state=InvoiceSyncState.SUBMITTED,
        status_lease_owner="worker_old",
        status_lease_expires_at=datetime.now(UTC) - timedelta(seconds=10),
        prepared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model)

    # Expired lease should be claimable
    claimed = await InvoiceStatusRepository.claim_status_lease(
        tenant_id="tenant_realdb",
        dispatch_id=sync_model.id,
        worker_id="worker_new",
        lease_duration_sec=60
    )
    assert claimed is not None
    assert claimed.status_lease_owner == "worker_new"

async def test_update_status_poll_result(migrated_db):
    sync_model = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id="tenant_realdb",
        invoice_id="inv_status_3",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:status_3",
        request_uuid=str(uuid.uuid4()),
        state=InvoiceSyncState.SUBMITTED,
        status_lease_owner="worker_1",
        status_lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
        prepared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model)

    success = await InvoiceStatusRepository.update_status_poll_result(
        tenant_id="tenant_realdb",
        dispatch_id=sync_model.id,
        worker_id="worker_1",
        update_fields={"state": InvoiceSyncState.ACCEPTED.value}
    )
    assert success is True

    record = await InvoiceSyncRepository.get_by_id("tenant_realdb", sync_model.id)
    assert record.state == InvoiceSyncState.ACCEPTED
    assert record.status_lease_owner is None

async def test_reconcile_status(migrated_db):
    sync_model = InvoiceSync(
        id=str(uuid.uuid4()),
        tenant_id="tenant_realdb",
        invoice_id="inv_status_4",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:status_4",
        request_uuid=str(uuid.uuid4()),
        state=InvoiceSyncState.SUBMITTED,
        reconciliation_required=True,
        prepared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await InvoiceSyncRepository.create_prepared("tenant_realdb", sync_model)

    success = await InvoiceStatusRepository.reconcile_status(
        tenant_id="tenant_realdb",
        dispatch_id=sync_model.id,
        target_state=InvoiceSyncState.ACCEPTED,
        note="Manual fix",
        actor="ops_user"
    )
    assert success is True

    record = await InvoiceSyncRepository.get_by_id("tenant_realdb", sync_model.id)
    assert record.state == InvoiceSyncState.ACCEPTED
    assert record.reconciliation_required is False
    assert record.reconciled_by == "ops_user"
    assert record.reconciliation_note == "Manual fix"
