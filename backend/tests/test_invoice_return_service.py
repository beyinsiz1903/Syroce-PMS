from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pymongo.errors import DuplicateKeyError

from core.integrations.invoice_return_service import (
    ReturnQuantityRequest,
    reserve_return_action,
)
from models.schemas.invoice_lifecycle import (
    ActionCreationResult,
    InvoiceLifecycleAction,
    InvoiceLifecycleActionState,
    InvoiceLifecycleActionType,
    InvoiceLifecycleDirection,
)


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    def start_transaction(self):
        return _Transaction()


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


def _action() -> InvoiceLifecycleAction:
    return InvoiceLifecycleAction(
        id="action-id",
        tenant_id="tenant-id",
        direction=InvoiceLifecycleDirection.INCOMING,
        source_invoice_id="invoice-id",
        source_provider_uuid="11112222-3333-4444-5555-666677778888",
        action_type=InvoiceLifecycleActionType.CREATE_INCOMING_RETURN,
        state=InvoiceLifecycleActionState.REQUESTED,
        request_uuid="request-id",
        idempotency_key="idempotency-key",
        request_fingerprint="fingerprint",
        return_type="FULL",
        requested_by="admin-id",
        requested_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_return_action_and_allocations_share_one_transaction_session():
    action = _action()
    session = _Session()
    client = SimpleNamespace(start_session=AsyncMock(return_value=session))
    database = SimpleNamespace()
    allocation = SimpleNamespace(id="allocation-id")
    with (
        patch(
            "core.integrations.invoice_return_service.core.database.client",
            client,
        ),
        patch(
            "core.integrations.invoice_return_service.get_db_for_tenant",
            return_value=database,
        ) as get_db,
        patch(
            "core.integrations.invoice_return_service.calculate_full_return_quantities",
            new=AsyncMock(
                return_value=[
                    ReturnQuantityRequest(
                        source_line_id="line-id",
                        quantity=Decimal("1"),
                    )
                ]
            ),
        ),
        patch(
            "core.integrations.invoice_return_service.InvoiceLifecycleRepository.insert_action",
            new=AsyncMock(),
        ) as insert_action,
        patch(
            "core.integrations.invoice_return_service._allocate_within_transaction",
            new=AsyncMock(return_value=[allocation]),
        ) as allocate,
    ):
        result = await reserve_return_action(action, "FULL")

    assert result.creation_result == ActionCreationResult.SUCCESS
    assert result.allocations == (allocation,)
    insert_action.assert_awaited_once_with(action, session=session)
    allocation_args = allocate.await_args.args
    assert allocation_args[0] is database
    assert allocation_args[1] is session
    assert allocation_args[2:4] == ("tenant-id", "invoice-id")
    assert len(allocation_args[4]) == 1
    assert allocation_args[4][0].return_action_id == "action-id"
    get_db.assert_called_once_with("tenant-id")


@pytest.mark.asyncio
async def test_idempotency_conflict_aborts_before_quantity_allocation():
    action = _action()
    session = _Session()
    client = SimpleNamespace(start_session=AsyncMock(return_value=session))
    duplicate = DuplicateKeyError(
        "duplicate",
        11000,
        {"keyPattern": {"idempotency_key": 1}},
    )
    allocate = AsyncMock()
    with (
        patch(
            "core.integrations.invoice_return_service.core.database.client",
            client,
        ),
        patch(
            "core.integrations.invoice_return_service.get_db_for_tenant",
            return_value=SimpleNamespace(),
        ),
        patch(
            "core.integrations.invoice_return_service.calculate_full_return_quantities",
            new=AsyncMock(
                return_value=[
                    ReturnQuantityRequest(
                        source_line_id="line-id",
                        quantity=Decimal("1"),
                    )
                ]
            ),
        ),
        patch(
            "core.integrations.invoice_return_service.InvoiceLifecycleRepository.insert_action",
            new=AsyncMock(side_effect=duplicate),
        ),
        patch(
            "core.integrations.invoice_return_service._allocate_within_transaction",
            new=allocate,
        ),
    ):
        result = await reserve_return_action(action, "FULL")

    assert result.creation_result == ActionCreationResult.IDEMPOTENCY_CONFLICT
    assert result.allocations == ()
    allocate.assert_not_awaited()
