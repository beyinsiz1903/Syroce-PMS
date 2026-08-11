import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pymongo.errors import PyMongoError

from api.routes.incoming_invoice_integrations import require_admin, router
from core.integrations.invoice_return_service import ReturnActionReservationResult
from core.tenant_db import TENANT_SCOPED_COLLECTIONS
from models.schemas.incoming_invoice import IncomingInvoiceProviderStatus
from models.schemas.invoice_lifecycle import (
    ActionCreationResult,
    InvoiceLifecycleActionType,
)

app = FastAPI()
app.include_router(router)


def _admin_user():
    return SimpleNamespace(id="admin-id", tenant_id="tenant-id")


app.dependency_overrides[require_admin] = _admin_user


def test_return_persistence_collections_are_tenant_scoped():
    assert {
        "invoice_return_allocations",
        "invoice_return_balances",
    }.issubset(TENANT_SCOPED_COLLECTIONS)


@pytest.fixture(autouse=True)
def enable_create_return(monkeypatch):
    monkeypatch.setenv("NILVERA_CREATE_RETURN_ENABLED", "true")


def _invoice(*, status=IncomingInvoiceProviderStatus.SUCCEED):
    return SimpleNamespace(
        provider_uuid="11112222-3333-4444-5555-666677778888",
        provider_status=status,
    )


@pytest.mark.asyncio
async def test_create_return_disabled_stops_before_database(monkeypatch):
    monkeypatch.delenv("NILVERA_CREATE_RETURN_ENABLED", raising=False)
    invoice_id = str(uuid.uuid4())
    get_invoice = AsyncMock()
    with patch(
        "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
        new=get_invoice,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/integrations/incoming-invoices/{invoice_id}/return",
                json={"return_type": "FULL", "request_uuid": str(uuid.uuid4())},
            )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "NILVERA_CREATE_RETURN_DISABLED"
    get_invoice.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_return_is_blocked_before_database_or_provider():
    invoice_id = str(uuid.uuid4())
    get_invoice = AsyncMock()
    reserve_action = AsyncMock()
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            new=get_invoice,
        ),
        patch(
            "api.routes.incoming_invoice_integrations.reserve_return_action",
            new=reserve_action,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/integrations/incoming-invoices/{invoice_id}/return",
                json={
                    "return_type": "PARTIAL",
                    "request_uuid": str(uuid.uuid4()),
                    "lines": [{"source_line_id": "line-id", "quantity": "1"}],
                },
            )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PARTIAL_RETURN_NOT_SUPPORTED_BY_PROVIDER_CONTRACT"
    get_invoice.assert_not_awaited()
    reserve_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_full_return_is_idempotent_and_reserves_only_once():
    invoice_id = str(uuid.uuid4())
    request_uuid = str(uuid.uuid4())
    captured: dict[str, object] = {}

    async def get_existing(_tenant_id, _idempotency_key):
        return captured.get("action")

    async def reserve(action, return_type):
        captured["action"] = action
        assert return_type == "FULL"
        return ReturnActionReservationResult(
            creation_result=ActionCreationResult.SUCCESS,
            allocations=(SimpleNamespace(), SimpleNamespace()),
        )

    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            new=AsyncMock(return_value=_invoice()),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            new=AsyncMock(side_effect=get_existing),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.initialize_balances_for_invoice",
            new=AsyncMock(),
        ) as initialize,
        patch(
            "api.routes.incoming_invoice_integrations.reserve_return_action",
            new=AsyncMock(side_effect=reserve),
        ) as reserve_mock,
        patch(
            "api.routes.incoming_invoice_integrations.count_return_allocations",
            new=AsyncMock(return_value=2),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = await client.post(
                f"/api/integrations/incoming-invoices/{invoice_id}/return",
                json={"return_type": "FULL", "request_uuid": request_uuid},
            )
            second = await client.post(
                f"/api/integrations/incoming-invoices/{invoice_id}/return",
                json={"return_type": "FULL", "request_uuid": request_uuid},
            )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["allocated_lines_count"] == 2
    initialize.assert_awaited_once_with("tenant-id", invoice_id)
    assert reserve_mock.await_count == 1
    action = captured["action"]
    assert action.action_type == InvoiceLifecycleActionType.CREATE_INCOMING_RETURN
    assert action.answer_guard_key == f"return:{invoice_id}"
    assert action.return_type == "FULL"


@pytest.mark.asyncio
async def test_provider_not_ready_creates_no_action_or_allocation():
    invoice_id = str(uuid.uuid4())
    reserve_action = AsyncMock()
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            new=AsyncMock(return_value=_invoice(status=IncomingInvoiceProviderStatus.WAITING)),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.reserve_return_action",
            new=reserve_action,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/integrations/incoming-invoices/{invoice_id}/return",
                json={"return_type": "FULL", "request_uuid": str(uuid.uuid4())},
            )

    assert response.status_code == 409
    assert response.json()["detail"] == "INVOICE_PROVIDER_STATUS_NOT_READY"
    reserve_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistence_failure_is_controlled_503_never_http_500():
    invoice_id = str(uuid.uuid4())
    with (
        patch(
            "api.routes.incoming_invoice_integrations.IncomingInvoiceRepository.get_by_id",
            new=AsyncMock(return_value=_invoice()),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.InvoiceLifecycleRepository.get_by_idempotency_key",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.routes.incoming_invoice_integrations.initialize_balances_for_invoice",
            new=AsyncMock(side_effect=PyMongoError("internal database detail")),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/integrations/incoming-invoices/{invoice_id}/return",
                json={"return_type": "FULL", "request_uuid": str(uuid.uuid4())},
            )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "RETURN_PERSISTENCE_UNAVAILABLE"
    assert "internal database detail" not in response.text
