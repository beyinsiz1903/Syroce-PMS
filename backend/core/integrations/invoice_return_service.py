import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Sequence

from pydantic import BaseModel

from core.integrations.invoice_return_repository import (
    ReturnAllocationRequest,
    allocate_return_quantities,
    update_allocation_state,
)
from core.tenant_db import get_db_for_tenant
from models.enums import ReturnAllocationState
from models.schemas.incoming_invoice import IncomingInvoiceLine
from models.schemas.invoicing import InvoiceReturnAllocation, InvoiceReturnBalance

logger = logging.getLogger(__name__)


class ReturnValidationError(Exception):
    pass


class ReturnQuantityRequest(BaseModel):
    source_line_id: str
    quantity: Decimal


async def initialize_balances_for_invoice(tenant_id: str, incoming_invoice_id: str) -> None:
    """
    Initializes InvoiceReturnBalance records for all lines of a newly ingested incoming invoice.
    This should be called during the ingestion of the incoming invoice.
    """
    db = get_db_for_tenant(tenant_id)

    # Check if balances already exist
    existing_count = await db.invoice_return_balances.count_documents({
        "tenant_id": tenant_id,
        "source_incoming_invoice_id": incoming_invoice_id
    })

    if existing_count > 0:
        return

    lines_cursor = db.incoming_invoice_lines.find({
        "tenant_id": tenant_id,
        "incoming_invoice_id": incoming_invoice_id
    })

    balances_to_insert = []
    async for line_doc in lines_cursor:
        line = IncomingInvoiceLine(**line_doc)
        bal = InvoiceReturnBalance(
            id=f"bal_{tenant_id}_{line.id}",
            tenant_id=tenant_id,
            source_incoming_invoice_id=incoming_invoice_id,
            source_line_id=line.id,
            original_quantity=line.quantity,
            reserved_quantity=Decimal("0.0"),
            confirmed_quantity=Decimal("0.0"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            version=1
        )
        bal_dict = bal.model_dump()
        bal_dict["original_quantity"] = str(bal_dict["original_quantity"])
        bal_dict["reserved_quantity"] = str(bal_dict["reserved_quantity"])
        bal_dict["confirmed_quantity"] = str(bal_dict["confirmed_quantity"])
        balances_to_insert.append(bal_dict)

    if balances_to_insert:
        await db.invoice_return_balances.insert_many(balances_to_insert)


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


async def handle_return_action_success(tenant_id: str, action_id: str) -> None:
    """
    Marks all allocations for a successful action as CONFIRMED.
    """
    db = get_db_for_tenant(tenant_id)
    cursor = db.invoice_return_allocations.find({
        "tenant_id": tenant_id,
        "return_action_id": action_id,
        "state": ReturnAllocationState.PROVIDER_PENDING
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
        "state": ReturnAllocationState.PROVIDER_PENDING
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
        "state": ReturnAllocationState.PROVIDER_PENDING
    })

    async for alloc_doc in cursor:
        alloc = InvoiceReturnAllocation(**alloc_doc)
        await update_allocation_state(tenant_id, alloc.id, ReturnAllocationState.RECONCILIATION_REQUIRED)
