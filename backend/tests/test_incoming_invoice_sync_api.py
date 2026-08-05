from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.incoming_invoice_integrations import require_admin, router
from core.integrations.incoming_invoice_sync_service import IncomingInvoiceSyncResult
from core.integrations.nilvera.errors import NilveraServerError
from models.schemas.incoming_invoice import (
    IncomingInvoice,
    IncomingInvoiceAnswerStatus,
    IncomingInvoiceLine,
    IncomingInvoiceProfile,
    IncomingInvoiceProviderStatus,
)
from models.schemas.invoice_sync import InvoiceProvider

app = FastAPI()
app.include_router(router)


def _admin_user():
    class AdminUser:
        id = "admin"
        tenant_id = "tenant-a"

    return AdminUser()


app.dependency_overrides[require_admin] = _admin_user


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _invoice() -> IncomingInvoice:
    now = datetime.now(UTC)
    return IncomingInvoice(
        id="local-invoice-id",
        tenant_id="tenant-a",
        provider=InvoiceProvider.NILVERA,
        provider_uuid="123e4567-e89b-12d3-a456-426614174000",
        invoice_number="TEST2026000000001",
        sender_vkn_tckn="1234567890",
        sender_title="Test Supplier",
        profile=IncomingInvoiceProfile.COMMERCIAL,
        answer_status=IncomingInvoiceAnswerStatus.PENDING,
        provider_status=IncomingInvoiceProviderStatus.WAITING,
        issue_date=now,
        received_at=now,
        payable_amount=Decimal("120.00"),
        currency="TRY",
        created_at=now,
        updated_at=now,
    )


def _line() -> IncomingInvoiceLine:
    now = datetime.now(UTC)
    return IncomingInvoiceLine(
        id="local-line-id",
        tenant_id="tenant-a",
        incoming_invoice_id="local-invoice-id",
        line_number=1,
        name="Service",
        quantity=Decimal("1"),
        unit_code="C62",
        unit_price=Decimal("100.00"),
        discount_amount=Decimal("0"),
        line_extension_amount=Decimal("100.00"),
        kdv_rate=Decimal("20"),
        kdv_amount=Decimal("20.00"),
        currency="TRY",
        created_at=now,
        updated_at=now,
    )


def test_list_is_tenant_scoped_and_keeps_pending_visible(client):
    with patch(
        "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.list_invoices",
        new=AsyncMock(return_value=([_invoice()], 1)),
    ) as list_mock:
        response = client.get("/api/integrations/incoming-invoices?provider_status=WAITING&limit=10")

    assert response.status_code == 200
    assert response.json()["items"][0]["provider_status"] == "WAITING"
    list_mock.assert_awaited_once()
    assert list_mock.await_args.args[0] == "tenant-a"


def test_detail_returns_active_lines(client):
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            new=AsyncMock(return_value=_invoice()),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.list_lines",
            new=AsyncMock(return_value=[_line()]),
        ) as lines_mock,
    ):
        response = client.get("/api/integrations/incoming-invoices/local-invoice-id")

    assert response.status_code == 200
    assert len(response.json()["lines"]) == 1
    lines_mock.assert_awaited_once_with("tenant-a", "local-invoice-id")


def test_sync_returns_counts_without_treating_pending_as_success_state(client):
    result = IncomingInvoiceSyncResult(
        invoices_seen=1,
        invoices_created=1,
        invoices_changed=0,
        lines_created=1,
        lines_changed=0,
        lines_deactivated=0,
        unknown_invoices=0,
        pending_invoices=1,
        provider_error_invoices=0,
    )
    with patch(
        "api.routes.incoming_invoice_integrations.IncomingInvoiceSyncService.sync_tenant",
        new=AsyncMock(return_value=result),
    ):
        response = client.post("/api/integrations/incoming-invoices/sync", json={})

    assert response.status_code == 200
    assert response.json()["pending_invoices"] == 1


def test_provider_500_is_not_returned_as_success_and_payload_is_hidden(client):
    secret_payload = "private-provider-payload"
    error = NilveraServerError("Provider request failed", raw_response=secret_payload)
    with patch(
        "api.routes.incoming_invoice_integrations.IncomingInvoiceSyncService.sync_tenant",
        new=AsyncMock(side_effect=error),
    ):
        response = client.post("/api/integrations/incoming-invoices/sync", json={})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "NILVERA_SERVER_ERROR"
    assert secret_payload not in response.text


def test_sync_rejects_naive_date(client):
    response = client.post(
        "/api/integrations/incoming-invoices/sync",
        json={"start_date": "2026-08-01T00:00:00"},
    )
    assert response.status_code == 422
