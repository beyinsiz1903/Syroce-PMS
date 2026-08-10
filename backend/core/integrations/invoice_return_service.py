import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Sequence

import pymongo.errors
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

import core.database
from core.integrations.invoice_lifecycle_repository import InvoiceLifecycleRepository
from core.integrations.invoice_return_repository import (
    PreconditionFailedError,
    ReturnAllocationRequest,
    _allocate_within_transaction,
    allocate_return_quantities,
    update_allocation_state,
)
from core.tenant_db import get_db_for_tenant
from models.enums import ReturnAllocationState
from models.schemas.incoming_invoice import IncomingInvoiceLine
from models.schemas.invoice_lifecycle import (
    ActionCreationResult,
    InvoiceLifecycleAction,
)
from models.schemas.invoicing import InvoiceReturnAllocation, InvoiceReturnBalance

logger = logging.getLogger(__name__)


class ReturnValidationError(Exception):
    pass


class ReturnQuantityRequest(BaseModel):
    source_line_id: str
    quantity: Decimal


@dataclass(frozen=True)
class ReturnActionReservationResult:
    creation_result: ActionCreationResult
    allocations: tuple[InvoiceReturnAllocation, ...] = ()


async def initialize_balances_for_invoice(tenant_id: str, incoming_invoice_id: str) -> None:
    """
    Initializes InvoiceReturnBalance records for all lines of a newly ingested incoming invoice.
    This should be called during the ingestion of the incoming invoice.
    """
    db = get_db_for_tenant(tenant_id)

    lines_cursor = db.incoming_invoice_lines.find(
        {
            "tenant_id": tenant_id,
            "incoming_invoice_id": incoming_invoice_id,
            "active": {"$ne": False},
        }
    )

    async for line_doc in lines_cursor:
        line = IncomingInvoiceLine(**line_doc)
        now = datetime.now(UTC)
        bal = InvoiceReturnBalance(
            id=f"bal_{tenant_id}_{line.id}",
            tenant_id=tenant_id,
            source_incoming_invoice_id=incoming_invoice_id,
            source_line_id=line.id,
            original_quantity=line.quantity,
            reserved_quantity=Decimal("0.0"),
            confirmed_quantity=Decimal("0.0"),
            created_at=now,
            updated_at=now,
            version=1,
        )
        bal_dict = bal.model_dump()
        bal_dict["original_quantity"] = str(bal_dict["original_quantity"])
        bal_dict["reserved_quantity"] = str(bal_dict["reserved_quantity"])
        bal_dict["confirmed_quantity"] = str(bal_dict["confirmed_quantity"])
        await db.invoice_return_balances.update_one(
            {
                "tenant_id": tenant_id,
                "source_incoming_invoice_id": incoming_invoice_id,
                "source_line_id": line.id,
            },
            {"$setOnInsert": bal_dict},
            upsert=True,
        )


async def calculate_full_return_quantities(
    tenant_id: str,
    incoming_invoice_id: str
) -> list[ReturnQuantityRequest]:
    """
    Calculates the maximum remaining returnable quantity for all lines of an incoming invoice.
    """
    db = get_db_for_tenant(tenant_id)

    cursor = db.invoice_return_balances.find({
        "tenant_id": tenant_id,
        "source_incoming_invoice_id": incoming_invoice_id
    })

    requests = []
    async for bal_doc in cursor:
        bal = InvoiceReturnBalance(**bal_doc)
        remaining = bal.original_quantity - (bal.reserved_quantity + bal.confirmed_quantity)
        if remaining > Decimal("0"):
            requests.append(ReturnQuantityRequest(source_line_id=bal.source_line_id, quantity=remaining))

    return requests


async def process_return_request(
    tenant_id: str,
    incoming_invoice_id: str,
    action_id: str,
    return_type: str,
    partial_requests: Sequence[ReturnQuantityRequest] | None = None
) -> list[InvoiceReturnAllocation]:
    """
    Main service method to process a return request (FULL or PARTIAL).
    Validates quantities and executes the CAS allocation.
    """
    if return_type == "FULL":
        requests_to_process = await calculate_full_return_quantities(tenant_id, incoming_invoice_id)
        if not requests_to_process:
            raise ReturnValidationError("No remaining quantities to return for FULL return.")
    elif return_type == "PARTIAL":
        if not partial_requests:
            raise ReturnValidationError("PARTIAL return requires quantity specifications.")
        requests_to_process = list(partial_requests)
    else:
        raise ReturnValidationError(f"Invalid return_type: {return_type}")

    # Decimal validation
    for req in requests_to_process:
        if req.quantity <= Decimal("0"):
            raise ReturnValidationError(f"Return quantity for line {req.source_line_id} must be > 0")

    alloc_requests = [
        ReturnAllocationRequest(
            source_line_id=r.source_line_id,
            quantity=r.quantity,
            return_action_id=action_id
        )
        for r in requests_to_process
    ]

    # This will fail-closed if there is not enough balance or transaction fails
    allocations = await allocate_return_quantities(
        tenant_id=tenant_id,
        source_incoming_invoice_id=incoming_invoice_id,
        allocations=alloc_requests
    )

    return allocations


async def reserve_return_action(
    action: InvoiceLifecycleAction,
    return_type: str,
) -> ReturnActionReservationResult:
    """Atomically persist a lifecycle action and all quantity reservations."""
    if return_type != "FULL":
        raise ReturnValidationError("Only FULL CreateReturn is supported by the provider contract.")

    requests = await calculate_full_return_quantities(
        action.tenant_id,
        action.source_invoice_id,
    )
    if not requests:
        raise ReturnValidationError("No remaining quantities to return for FULL return.")

    allocation_requests = [
        ReturnAllocationRequest(
            source_line_id=request.source_line_id,
            quantity=request.quantity,
            return_action_id=action.id,
        )
        for request in requests
    ]
    db = get_db_for_tenant(action.tenant_id)

    try:
        async with await core.database.client.start_session() as session:
            async with session.start_transaction():
                await InvoiceLifecycleRepository.insert_action(action, session=session)
                allocations = await _allocate_within_transaction(
                    db,
                    session,
                    action.tenant_id,
                    action.source_invoice_id,
                    allocation_requests,
                )
        return ReturnActionReservationResult(
            creation_result=ActionCreationResult.SUCCESS,
            allocations=tuple(allocations),
        )
    except DuplicateKeyError as error:
        return ReturnActionReservationResult(
            creation_result=InvoiceLifecycleRepository.classify_duplicate_error(error),
        )
    except pymongo.errors.OperationFailure as error:
        if "Transaction" in str(error) or error.code in (20, 246):
            raise PreconditionFailedError(
                "MongoDB transaction support is required for return allocation"
            ) from error
        raise


async def count_return_allocations(tenant_id: str, action_id: str) -> int:
    db = get_db_for_tenant(tenant_id)
    return await db.invoice_return_allocations.count_documents(
        {
            "tenant_id": tenant_id,
            "return_action_id": action_id,
        }
    )


async def prepare_return_action_for_provider(tenant_id: str, action_id: str) -> bool:
    """Move every reserved allocation to provider-pending before the one write."""
    db = get_db_for_tenant(tenant_id)
    allocation_count = await db.invoice_return_allocations.count_documents(
        {
            "tenant_id": tenant_id,
            "return_action_id": action_id,
        }
    )
    if allocation_count == 0 or allocation_count > 1000:
        return False

    docs = await db.invoice_return_allocations.find(
        {
            "tenant_id": tenant_id,
            "return_action_id": action_id,
        }
    ).to_list(length=1000)
    if len(docs) != allocation_count:
        return False

    for doc in docs:
        allocation = InvoiceReturnAllocation(**doc)
        if allocation.state == ReturnAllocationState.RESERVED:
            updated = await update_allocation_state(
                tenant_id,
                allocation.id,
                ReturnAllocationState.PROVIDER_PENDING,
            )
            if updated is None:
                return False
        elif allocation.state != ReturnAllocationState.PROVIDER_PENDING:
            return False

    pending_count = await db.invoice_return_allocations.count_documents(
        {
            "tenant_id": tenant_id,
            "return_action_id": action_id,
            "state": ReturnAllocationState.PROVIDER_PENDING.value,
        }
    )
    return pending_count == len(docs)


async def handle_return_action_success(tenant_id: str, action_id: str) -> None:
    """
    Marks all allocations for a successful action as CONFIRMED.
    """
    db = get_db_for_tenant(tenant_id)
    cursor = db.invoice_return_allocations.find({
        "tenant_id": tenant_id,
        "return_action_id": action_id,
        "state": {
            "$in": [
                ReturnAllocationState.PROVIDER_PENDING.value,
                ReturnAllocationState.RECONCILIATION_REQUIRED.value,
            ]
        },
    })

    async for alloc_doc in cursor:
        alloc = InvoiceReturnAllocation(**alloc_doc)
        await update_allocation_state(tenant_id, alloc.id, ReturnAllocationState.CONFIRMED)


async def handle_return_action_validation_failure(tenant_id: str, action_id: str) -> None:
    """
    Marks allocations as RELEASED when the provider rejects them cleanly (e.g. 400/422).
    """
    db = get_db_for_tenant(tenant_id)
    cursor = db.invoice_return_allocations.find({
        "tenant_id": tenant_id,
        "return_action_id": action_id,
        "state": {
            "$in": [
                ReturnAllocationState.RESERVED.value,
                ReturnAllocationState.PROVIDER_PENDING.value,
            ]
        },
    })

    async for alloc_doc in cursor:
        alloc = InvoiceReturnAllocation(**alloc_doc)
        await update_allocation_state(tenant_id, alloc.id, ReturnAllocationState.RELEASED)


async def handle_return_action_unknown_failure(tenant_id: str, action_id: str) -> None:
    """
    Marks allocations as RECONCILIATION_REQUIRED for timeouts or 5xx errors.
    """
    db = get_db_for_tenant(tenant_id)
    cursor = db.invoice_return_allocations.find({
        "tenant_id": tenant_id,
        "return_action_id": action_id,
        "state": ReturnAllocationState.PROVIDER_PENDING.value,
    })

    async for alloc_doc in cursor:
        alloc = InvoiceReturnAllocation(**alloc_doc)
        await update_allocation_state(tenant_id, alloc.id, ReturnAllocationState.RECONCILIATION_REQUIRED)
