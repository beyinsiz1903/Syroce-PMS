import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Sequence

import pymongo.errors
from motor.motor_asyncio import AsyncIOMotorClientSession, AsyncIOMotorDatabase
from pydantic import BaseModel

import core.database
from core.tenant_db import get_db_for_tenant
from models.enums import ReturnAllocationState
from models.schemas.invoicing import InvoiceReturnAllocation, InvoiceReturnBalance

logger = logging.getLogger(__name__)


class CASFailedError(Exception):
    """Raised when CAS or transaction validation fails."""
    pass


class PreconditionFailedError(Exception):
    """Raised when MongoDB transaction support is missing or another precondition fails."""
    pass


class ReturnAllocationRequest(BaseModel):
    source_line_id: str
    quantity: Decimal
    return_action_id: str


async def allocate_return_quantities(
    tenant_id: str,
    source_incoming_invoice_id: str,
    allocations: Sequence[ReturnAllocationRequest]
) -> list[InvoiceReturnAllocation]:
    """
    Atomically allocates return quantities from invoice balances.
    Must be run in a MongoDB transaction. If transactions are not supported,
    fails with PreconditionFailedError.
    """
    db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
    
    # Check if replica set (transactions) are supported
    # In a real environment, we'd check client status, but for Motor we try to start session.
    try:
        async with await core.database.client.start_session() as session:
            try:
                async with session.start_transaction():
                    return await _allocate_within_transaction(
                        db, session, tenant_id, source_incoming_invoice_id, allocations
                    )
            except pymongo.errors.OperationFailure as e:
                # Code 20 (IllegalOperation) or similar often means standalone server
                if "Transaction" in str(e) or e.code in (20, 246):
                    logger.error(f"MongoDB transactions not supported: {e}")
                    raise PreconditionFailedError("MongoDB transaction support is required for return allocation") from e
                raise
    except pymongo.errors.OperationFailure as e:
        if "Transaction" in str(e) or e.code in (20, 246):
            raise PreconditionFailedError("MongoDB transaction support is required for return allocation") from e
        raise


async def _allocate_within_transaction(
    db: AsyncIOMotorDatabase,
    session: AsyncIOMotorClientSession,
    tenant_id: str,
    source_incoming_invoice_id: str,
    allocations: Sequence[ReturnAllocationRequest]
) -> list[InvoiceReturnAllocation]:
    now = datetime.now(UTC)
    results: list[InvoiceReturnAllocation] = []

    for alloc_req in allocations:
        # 1. Fetch balance document
        balance_doc = await db.invoice_return_balances.find_one(
            {
                "tenant_id": tenant_id,
                "source_incoming_invoice_id": source_incoming_invoice_id,
                "source_line_id": alloc_req.source_line_id
            },
            session=session
        )
        
        if not balance_doc:
            raise CASFailedError(f"Balance not found for line {alloc_req.source_line_id}")
            
        balance = InvoiceReturnBalance(**balance_doc)
        
        # 2. Check quantities
        total_used = balance.reserved_quantity + balance.confirmed_quantity
        if total_used + alloc_req.quantity > balance.original_quantity:
            raise CASFailedError(
                f"Insufficient quantity for line {alloc_req.source_line_id}. "
                f"Requested: {alloc_req.quantity}, Available: {balance.original_quantity - total_used}"
            )
            
        # 3. Update balance (CAS update with version)
        update_res = await db.invoice_return_balances.update_one(
            {
                "tenant_id": tenant_id,
                "source_line_id": alloc_req.source_line_id,
                "version": balance.version
            },
            {
                "$set": {
                    "reserved_quantity": str(balance.reserved_quantity + alloc_req.quantity),
                    "version": balance.version + 1
                }
            },
            session=session
        )
        
        if update_res.modified_count != 1:
            raise CASFailedError(f"Concurrent update detected for line {alloc_req.source_line_id}")
            
        # 4. Create allocation record
        allocation = InvoiceReturnAllocation(
            id=f"alloc_{tenant_id}_{alloc_req.source_line_id}_{now.timestamp()}",
            tenant_id=tenant_id,
            source_incoming_invoice_id=source_incoming_invoice_id,
            source_line_id=alloc_req.source_line_id,
            return_action_id=alloc_req.return_action_id,
            quantity=alloc_req.quantity,
            state=ReturnAllocationState.RESERVED,
            created_at=now,
            updated_at=now
        )
        
        await db.invoice_return_allocations.insert_one(
            allocation.model_dump(mode="json"),
            session=session
        )
        results.append(allocation)

    return results


async def update_allocation_state(
    tenant_id: str,
    allocation_id: str,
    new_state: ReturnAllocationState
) -> InvoiceReturnAllocation | None:
    """
    Updates the state of an allocation. If moving to CONFIRMED or RELEASED,
    adjusts the balance accordingly.
    """
    db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
    
    async with await core.database.client.start_session() as session:
        async with session.start_transaction():
            alloc_doc = await db.invoice_return_allocations.find_one(
                {"tenant_id": tenant_id, "id": allocation_id},
                session=session
            )
            if not alloc_doc:
                return None
                
            allocation = InvoiceReturnAllocation(**alloc_doc)
            old_state = allocation.state
            
            if old_state == new_state:
                return allocation
                
            now = datetime.now(UTC)
            
            # Update allocation state
            await db.invoice_return_allocations.update_one(
                {"tenant_id": tenant_id, "id": allocation_id},
                {"$set": {"state": new_state, "updated_at": now}},
                session=session
            )
            allocation.state = new_state
            allocation.updated_at = now
            
            # Adjust balances if necessary
            if old_state in (ReturnAllocationState.RESERVED, ReturnAllocationState.PROVIDER_PENDING):
                balance_doc = await db.invoice_return_balances.find_one(
                    {"tenant_id": tenant_id, "source_line_id": allocation.source_line_id},
                    session=session
                )
                if balance_doc:
                    bal = InvoiceReturnBalance(**balance_doc)
                    if new_state == ReturnAllocationState.CONFIRMED:
                        await db.invoice_return_balances.update_one(
                            {"tenant_id": tenant_id, "source_line_id": allocation.source_line_id, "version": bal.version},
                            {
                                "$set": {
                                    "reserved_quantity": str(bal.reserved_quantity - allocation.quantity),
                                    "confirmed_quantity": str(bal.confirmed_quantity + allocation.quantity),
                                    "version": bal.version + 1,
                                    "updated_at": now
                                }
                            },
                            session=session
                        )
                    elif new_state == ReturnAllocationState.RELEASED:
                        await db.invoice_return_balances.update_one(
                            {"tenant_id": tenant_id, "source_line_id": allocation.source_line_id, "version": bal.version},
                            {
                                "$set": {
                                    "reserved_quantity": str(bal.reserved_quantity - allocation.quantity),
                                    "version": bal.version + 1,
                                    "updated_at": now
                                }
                            },
                            session=session
                        )
            
            return allocation
