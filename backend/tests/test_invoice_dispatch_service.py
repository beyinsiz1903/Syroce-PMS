from datetime import UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from core.integrations.errors import IntegrationConflictError, IntegrationNotFoundError, IntegrationValidationError
from core.integrations.invoice_dispatch_service import InvoiceDispatchService
from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider


@pytest.fixture
def mock_db(monkeypatch):
    db_mock = MagicMock()

    import core.integrations.invoice_dispatch_service as ids
    import core.integrations.invoice_sync_repository as isr

    monkeypatch.setattr(ids, "get_db_for_tenant", lambda t: db_mock)
    monkeypatch.setattr(isr, "get_db_for_tenant", lambda t: db_mock)

    return db_mock

@pytest.mark.asyncio
async def test_prepare_dispatch_success(mock_db, monkeypatch):
    mock_db.invoices.find_one = AsyncMock(return_value={
        "id": "inv_123",
        "tenant_id": "tenant_1",
        "invoice_type": "SATIS"
    })

    mock_db.invoice_sync.insert_one = AsyncMock()

    result = await InvoiceDispatchService.prepare_dispatch(
        tenant_id="tenant_1",
        invoice_id="inv_123",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE
    )

    assert result.created is True
    assert isinstance(result.request_uuid, UUID)
    assert result.dispatch_id is not None
    assert result.idempotency_key is not None
    mock_db.invoice_sync.insert_one.assert_called_once()

@pytest.mark.asyncio
async def test_prepare_dispatch_unsupported_kind():
    with pytest.raises(IntegrationValidationError) as exc:
        await InvoiceDispatchService.prepare_dispatch(
            tenant_id="t1",
            invoice_id="i1",
            provider=InvoiceProvider.NILVERA,
            document_kind="E_ARCHIVE" # type: ignore
        )
    assert "Unsupported document kind" in str(exc.value)

@pytest.mark.asyncio
async def test_prepare_dispatch_invoice_not_found(mock_db, monkeypatch):
    mock_db.invoices.find_one = AsyncMock(return_value=None)
    with pytest.raises(IntegrationNotFoundError):
        await InvoiceDispatchService.prepare_dispatch(
            tenant_id="t1",
            invoice_id="i1",
            provider=InvoiceProvider.NILVERA,
            document_kind=InvoiceDocumentKind.E_INVOICE
        )

@pytest.mark.asyncio
async def test_prepare_dispatch_unsupported_invoice_type(mock_db, monkeypatch):
    mock_db.invoices.find_one = AsyncMock(return_value={
        "id": "inv_1",
        "tenant_id": "t1",
        "invoice_type": "IADE"
    })
    with pytest.raises(IntegrationValidationError) as exc:
        await InvoiceDispatchService.prepare_dispatch(
            tenant_id="t1",
            invoice_id="inv_1",
            provider=InvoiceProvider.NILVERA,
            document_kind=InvoiceDocumentKind.E_INVOICE
        )
    assert "Only SATIS invoices are supported" in str(exc.value)

@pytest.mark.asyncio
async def test_prepare_dispatch_duplicate_recovery(mock_db, monkeypatch):
    mock_db.invoices.find_one = AsyncMock(return_value={
        "id": "inv_123",
        "tenant_id": "tenant_1",
        "invoice_type": "SATIS"
    })

    from pymongo.errors import DuplicateKeyError
    mock_db.invoice_sync.insert_one = AsyncMock(side_effect=DuplicateKeyError("E11000 duplicate key error"))

    from datetime import datetime
    # Mock find_one for the recovery
    mock_db.invoice_sync.find_one = AsyncMock(return_value={
        "id": "existing_disp",
        "tenant_id": "tenant_1",
        "invoice_id": "inv_123",
        "provider": "NILVERA",
        "document_kind": "E_INVOICE",
        "idempotency_key": "v1:xxx",
        "request_uuid": "12345678-1234-5678-1234-567812345678",
        "state": "PREPARED",
        "prepared_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "version": 1
    })

    result = await InvoiceDispatchService.prepare_dispatch(
        tenant_id="tenant_1",
        invoice_id="inv_123",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE
    )

    assert result.created is False
    assert result.dispatch_id == "existing_disp"
    assert str(result.request_uuid) == "12345678-1234-5678-1234-567812345678"

@pytest.mark.asyncio
async def test_prepare_dispatch_duplicate_conflict(mock_db, monkeypatch):
    mock_db.invoices.find_one = AsyncMock(return_value={
        "id": "inv_123",
        "tenant_id": "tenant_1",
        "invoice_type": "SATIS"
    })
    from pymongo.errors import DuplicateKeyError
    mock_db.invoice_sync.insert_one = AsyncMock(side_effect=DuplicateKeyError("E11000 duplicate key error"))

    # Recovery returns None, meaning collision was on UUID or idempotency but NOT business key
    mock_db.invoice_sync.find_one = AsyncMock(return_value=None)

    with pytest.raises(IntegrationConflictError):
        await InvoiceDispatchService.prepare_dispatch(
            tenant_id="tenant_1",
            invoice_id="inv_123",
            provider=InvoiceProvider.NILVERA,
            document_kind=InvoiceDocumentKind.E_INVOICE
        )

