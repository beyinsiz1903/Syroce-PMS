from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.invoice_integrations import router
from core.security import get_current_user
from models.enums import UserRole
from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider, InvoiceSync, InvoiceSyncState

app = FastAPI()
app.include_router(router)

def mock_get_current_user():
    user = MagicMock()
    user.id = "ops_user_01"
    user.tenant_id = "tenant_1"
    user.role = UserRole.ADMIN
    return user

app.dependency_overrides[get_current_user] = mock_get_current_user

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

def create_mock_sync(reconciliation_required=False, state=InvoiceSyncState.SUBMITTED):
    now = datetime.now(UTC)
    return InvoiceSync(
        id="sync-api-1",
        tenant_id="tenant_1",
        invoice_id="inv-1",
        provider=InvoiceProvider.NILVERA,
        document_kind=InvoiceDocumentKind.E_INVOICE,
        idempotency_key="v1:hash",
        request_uuid="req-123",
        state=state,
        provider_document_id="doc-123",
        reconciliation_required=reconciliation_required,
        prepared_at=now,
        created_at=now,
        updated_at=now,
    )

@patch("api.routes.invoice_integrations.InvoiceSyncRepository")
def test_get_invoice_status(mock_repo, client):
    mock_repo.get_by_id = AsyncMock(return_value=create_mock_sync())

    response = client.get("/api/integrations/invoices/sync-api-1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "sync-api-1"
    assert data["state"] == "SUBMITTED"

@patch("api.routes.invoice_integrations.InvoiceSyncRepository")
def test_get_invoice_status_not_found(mock_repo, client):
    mock_repo.get_by_id = AsyncMock(return_value=None)

    response = client.get("/api/integrations/invoices/unknown-id/status")
    assert response.status_code == 404

@patch("api.routes.invoice_integrations.InvoiceSyncRepository")
@patch("api.routes.invoice_integrations.InvoiceStatusRepository")
@patch("api.routes.invoice_integrations.event_bus")
def test_reconcile_invoice_status_success(mock_event_bus, mock_status_repo, mock_sync_repo, client):
    record = create_mock_sync(reconciliation_required=True)
    mock_sync_repo.get_by_id = AsyncMock(return_value=record)
    mock_status_repo.reconcile_status = AsyncMock(return_value=True)

    payload = {
        "resolution": "MARK_ACCEPTED",
        "note": "Ops confirmed manually"
    }

    async def mock_publish(*args, **kwargs):
        mock_publish.called = True

    mock_event_bus.publish = mock_publish
    mock_publish.called = False

    response = client.post("/api/integrations/invoices/sync-api-1/reconcile", json=payload)
    assert response.status_code == 200
    assert response.json()["new_state"] == "ACCEPTED"
    assert mock_publish.called

@patch("api.routes.invoice_integrations.InvoiceSyncRepository")
def test_reconcile_invoice_status_not_required(mock_sync_repo, client):
    record = create_mock_sync(reconciliation_required=False)
    mock_sync_repo.get_by_id = AsyncMock(return_value=record)

    payload = {
        "resolution": "MARK_ACCEPTED",
        "note": "Should fail"
    }

    response = client.post("/api/integrations/invoices/sync-api-1/reconcile", json=payload)
    assert response.status_code == 400
    assert "not require reconciliation" in response.json()["detail"]

@patch("api.routes.invoice_integrations.InvoiceSyncRepository")
@patch("api.routes.invoice_integrations.get_db_for_tenant")
def test_retry_invoice_status(mock_get_db, mock_sync_repo, client):
    record = create_mock_sync(state=InvoiceSyncState.SUBMITTED)
    mock_sync_repo.get_by_id = AsyncMock(return_value=record)

    async def mock_update_one(*args, **kwargs):
        mock_update_one.called = True

    mock_db = MagicMock()
    mock_db.invoice_sync.update_one = mock_update_one
    mock_update_one.called = False
    mock_get_db.return_value = mock_db

    response = client.post("/api/integrations/invoices/sync-api-1/retry-status")
    assert response.status_code == 200
    assert mock_update_one.called
