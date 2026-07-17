from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from core.tenant_db import get_db_for_tenant
from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus


class IncomingInvoiceRepository:
    """Repository for incoming purchase invoices."""

    @staticmethod
    async def save(invoice: IncomingInvoice) -> None:
        db: AsyncIOMotorDatabase = get_db_for_tenant(invoice.tenant_id)
        doc = invoice.model_dump(by_alias=True)
        await db.incoming_invoices.insert_one(doc)

    @staticmethod
    async def get_by_id(tenant_id: str, invoice_id: str) -> IncomingInvoice | None:
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        doc = await db.incoming_invoices.find_one({"id": invoice_id, "tenant_id": tenant_id})
        if not doc:
            return None
        return IncomingInvoice.model_validate(doc)

    @staticmethod
    async def update_answer_status(tenant_id: str, invoice_id: str, new_status: IncomingInvoiceAnswerStatus) -> bool:
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        result = await db.incoming_invoices.update_one(
            {"id": invoice_id, "tenant_id": tenant_id},
            {
                "$set": {
                    "answer_status": new_status.value,
                    "updated_at": datetime.now(UTC),
                },
                "$inc": {"version": 1},
            },
        )
        return result.modified_count > 0
