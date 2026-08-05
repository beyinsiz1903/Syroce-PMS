import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
from models.schemas.incoming_invoice import (
    IncomingInvoice,
    IncomingInvoiceAnswerStatus,
    IncomingInvoiceLine,
    IncomingInvoiceProfile,
    IncomingInvoiceProviderStatus,
)
from models.schemas.invoice_sync import InvoiceProvider

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
        pytest.skip("MongoDB unavailable")
    return client


@pytest.fixture
async def migrated_db(monkeypatch):
    client = await _mongo_or_skip()
    raw_db = client[f"test_incoming_sync_{uuid.uuid4().hex[:8]}"]

    import core.database
    from core.tenant_db import TenantAwareDBProxy

    monkeypatch.setattr(core.database, "db", TenantAwareDBProxy(raw_db))
    monkeypatch.setattr(core.database, "_raw_db", raw_db)

    from bootstrap.migrations.versions.v005_incoming_invoice_lifecycle import MIGRATION as v005
    from bootstrap.migrations.versions.v007_f2_create_return_models import MIGRATION as v007
    from bootstrap.migrations.versions.v009_incoming_invoice_sync import MIGRATION as v009

    await v005.up(raw_db)
    await v007.up(raw_db)
    await v009.up(raw_db)
    yield raw_db

    await client.drop_database(raw_db.name)
    client.close()


def _snapshot(
    *,
    tenant_id: str = "tenant-a",
    provider_status: IncomingInvoiceProviderStatus = IncomingInvoiceProviderStatus.SUCCEED,
    line_price: Decimal = Decimal("100.00"),
    line_count: int = 2,
) -> tuple[IncomingInvoice, tuple[IncomingInvoiceLine, ...]]:
    now = datetime.now(UTC)
    invoice_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    invoice = IncomingInvoice(
        id=invoice_id,
        tenant_id=tenant_id,
        provider=InvoiceProvider.NILVERA,
        provider_uuid="123e4567-e89b-12d3-a456-426614174000",
        invoice_number="TEST2026000000001",
        sender_vkn_tckn="1234567890",
        sender_title="Test Supplier",
        profile=IncomingInvoiceProfile.COMMERCIAL,
        answer_status=IncomingInvoiceAnswerStatus.APPROVED,
        provider_status=provider_status,
        provider_gib_code="1200",
        issue_date=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        received_at=now,
        payable_amount=Decimal("120.00"),
        currency="TRY",
        created_at=now,
        updated_at=now,
    )
    lines = tuple(
        IncomingInvoiceLine(
            id=f"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb{line_number}",
            tenant_id=tenant_id,
            incoming_invoice_id=invoice_id,
            provider_line_id=str(line_number),
            line_number=line_number,
            name=f"Line {line_number}",
            quantity=Decimal("1"),
            unit_code="C62",
            unit_price=line_price,
            discount_amount=Decimal("0"),
            line_extension_amount=line_price,
            kdv_rate=Decimal("20"),
            kdv_amount=Decimal("20.00"),
            currency="TRY",
            created_at=now,
            updated_at=now,
        )
        for line_number in range(1, line_count + 1)
    )
    return invoice, lines


async def test_snapshot_upsert_is_idempotent_and_tenant_scoped(migrated_db):
    invoice, lines = _snapshot()
    first = await IncomingInvoiceRepository.upsert_snapshot(invoice, lines)
    duplicate_invoice, duplicate_lines = _snapshot()
    second = await IncomingInvoiceRepository.upsert_snapshot(
        duplicate_invoice,
        duplicate_lines,
    )

    assert first.created is True
    assert first.lines_created == 2
    assert second.created is False
    assert second.changed is False
    assert second.lines_created == 0
    assert second.lines_changed == 0
    assert await migrated_db.incoming_invoices.count_documents({}) == 1
    assert await migrated_db.incoming_invoice_lines.count_documents({}) == 2
    assert await IncomingInvoiceRepository.get_by_id("tenant-b", invoice.id) is None


async def test_snapshot_updates_changes_and_deactivates_stale_lines(migrated_db):
    invoice, lines = _snapshot()
    await IncomingInvoiceRepository.upsert_snapshot(invoice, lines)

    changed_invoice, changed_lines = _snapshot(
        provider_status=IncomingInvoiceProviderStatus.ERROR,
        line_price=Decimal("110.00"),
        line_count=1,
    )
    result = await IncomingInvoiceRepository.upsert_snapshot(
        changed_invoice,
        changed_lines,
    )

    assert result.changed is True
    assert result.lines_changed == 1
    assert result.lines_deactivated == 1
    persisted = await IncomingInvoiceRepository.get_by_id("tenant-a", invoice.id)
    assert persisted is not None
    assert persisted.provider_status == IncomingInvoiceProviderStatus.ERROR
    active_lines = await IncomingInvoiceRepository.list_lines("tenant-a", invoice.id)
    assert len(active_lines) == 1
    assert active_lines[0].unit_price == Decimal("110.00")


async def test_snapshot_attaches_lines_to_preexisting_local_invoice_id(migrated_db):
    existing_invoice, _ = _snapshot()
    existing_invoice = existing_invoice.model_copy(update={"id": "legacy-local-id"})
    await IncomingInvoiceRepository.save(existing_invoice)

    desired_invoice, desired_lines = _snapshot(line_count=1)
    result = await IncomingInvoiceRepository.upsert_snapshot(
        desired_invoice,
        desired_lines,
    )

    assert result.invoice.id == "legacy-local-id"
    persisted_lines = await IncomingInvoiceRepository.list_lines(
        "tenant-a",
        "legacy-local-id",
    )
    assert len(persisted_lines) == 1
    assert persisted_lines[0].incoming_invoice_id == "legacy-local-id"


async def test_v009_indexes_are_created_and_idempotent(migrated_db):
    from bootstrap.migrations.versions.v009_incoming_invoice_sync import MIGRATION

    await MIGRATION.up(migrated_db)
    invoice_indexes = await migrated_db.incoming_invoices.index_information()
    state_indexes = await migrated_db.incoming_invoice_sync_state.index_information()

    assert "idx_incoming_invoices_tenant_issue_date" in invoice_indexes
    assert "idx_incoming_sync_state_tenant_provider_unique" in state_indexes
    assert state_indexes["idx_incoming_sync_state_tenant_provider_unique"]["unique"] is True


async def test_periodic_sync_lease_allows_only_one_worker(migrated_db):
    from core.integrations.incoming_invoice_sync_worker import IncomingInvoiceSyncWorker

    first_worker = IncomingInvoiceSyncWorker()
    second_worker = IncomingInvoiceSyncWorker()

    first_claim = await first_worker._claim_due_sync("tenant-a")
    second_claim = await second_worker._claim_due_sync("tenant-a")

    assert first_claim is not None
    assert second_claim is None
