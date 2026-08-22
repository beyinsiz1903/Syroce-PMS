from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from bson.decimal128 import Decimal128
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core.tenant_db import get_db_for_tenant
from models.schemas.incoming_invoice import (
    IncomingInvoice,
    IncomingInvoiceAnswerStatus,
    IncomingInvoiceLine,
    IncomingInvoiceProfile,
    IncomingInvoiceProviderStatus,
)


@dataclass(frozen=True)
class IncomingInvoiceUpsertResult:
    invoice: IncomingInvoice
    created: bool
    changed: bool
    lines_created: int
    lines_changed: int
    lines_deactivated: int


def _mongo_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, BaseModel):
        return _mongo_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _mongo_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mongo_value(item) for item in value]
    return value


def _model_doc(model) -> dict[str, Any]:
    return _mongo_value(model.model_dump(mode="python"))


def _comparison_value(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return _mongo_value(value)


class IncomingInvoiceRepository:
    """Tenant-scoped persistence for incoming purchase invoices."""

    _INVOICE_MUTABLE_FIELDS = (
        "invoice_number",
        "sender_vkn_tckn",
        "sender_title",
        "profile",
        "answer_status",
        "provider_status",
        "provider_gib_code",
        "issue_date",
        "issue_date_timezone_assumed",
        "payable_amount",
        "currency",
        "exchange_rate",
    )
    _LINE_MUTABLE_FIELDS = (
        "provider_line_id",
        "name",
        "quantity",
        "unit_code",
        "unit_price",
        "discount_amount",
        "line_extension_amount",
        "kdv_rate",
        "kdv_amount",
        "other_taxes",
        "currency",
        "active",
    )

    @staticmethod
    async def save(invoice: IncomingInvoice) -> None:
        db: AsyncIOMotorDatabase = get_db_for_tenant(invoice.tenant_id)
        await db.incoming_invoices.insert_one(_model_doc(invoice))

    @staticmethod
    async def get_by_id(tenant_id: str, invoice_id: str) -> IncomingInvoice | None:
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        doc = await db.incoming_invoices.find_one({"id": invoice_id, "tenant_id": tenant_id})
        return IncomingInvoice.model_validate(doc) if doc else None

    @staticmethod
    async def get_by_provider_uuid(tenant_id: str, provider_uuid: str) -> IncomingInvoice | None:
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        doc = await db.incoming_invoices.find_one({"tenant_id": tenant_id, "provider_uuid": provider_uuid})
        return IncomingInvoice.model_validate(doc) if doc else None

    @staticmethod
    async def list_invoices(
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        profile: IncomingInvoiceProfile | None = None,
        answer_status: IncomingInvoiceAnswerStatus | None = None,
        provider_status: IncomingInvoiceProviderStatus | None = None,
    ) -> tuple[list[IncomingInvoice], int]:
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if profile is not None:
            query["profile"] = profile.value
        if answer_status is not None:
            query["answer_status"] = answer_status.value
        if provider_status is not None:
            query["provider_status"] = provider_status.value

        total = await db.incoming_invoices.count_documents(query)
        docs = await db.incoming_invoices.find(query).sort([("issue_date", -1), ("id", 1)]).skip(offset).limit(limit).to_list(length=limit)
        return [IncomingInvoice.model_validate(doc) for doc in docs], total

    @staticmethod
    async def list_lines(tenant_id: str, invoice_id: str) -> list[IncomingInvoiceLine]:
        db: AsyncIOMotorDatabase = get_db_for_tenant(tenant_id)
        docs = await (
            db.incoming_invoice_lines.find(
                {
                    "tenant_id": tenant_id,
                    "incoming_invoice_id": invoice_id,
                    "active": {"$ne": False},
                }
            )
            .sort("line_number", 1)
            .to_list(length=None)
        )
        return [IncomingInvoiceLine.model_validate(doc) for doc in docs]

    @classmethod
    async def upsert_snapshot(
        cls,
        invoice: IncomingInvoice,
        lines: tuple[IncomingInvoiceLine, ...],
    ) -> IncomingInvoiceUpsertResult:
        if any(line.tenant_id != invoice.tenant_id for line in lines):
            raise ValueError("Incoming invoice line tenant mismatch")
        if any(line.incoming_invoice_id != invoice.id for line in lines):
            raise ValueError("Incoming invoice line parent mismatch")
        if len({line.line_number for line in lines}) != len(lines):
            raise ValueError("Incoming invoice line numbers must be unique")

        persisted, created, changed = await cls._upsert_invoice(invoice)
        persisted_lines = tuple(line.model_copy(update={"incoming_invoice_id": persisted.id}) if line.incoming_invoice_id != persisted.id else line for line in lines)
        lines_created = 0
        lines_changed = 0
        for line in persisted_lines:
            line_created, line_changed = await cls._upsert_line(line)
            lines_created += int(line_created)
            lines_changed += int(line_changed)

        db: AsyncIOMotorDatabase = get_db_for_tenant(invoice.tenant_id)
        active_line_numbers = [line.line_number for line in persisted_lines]
        stale_result = await db.incoming_invoice_lines.update_many(
            {
                "tenant_id": invoice.tenant_id,
                "incoming_invoice_id": persisted.id,
                "active": {"$ne": False},
                "line_number": {"$nin": active_line_numbers},
            },
            {
                "$set": {"active": False, "updated_at": datetime.now(UTC)},
                "$inc": {"version": 1},
            },
        )

        return IncomingInvoiceUpsertResult(
            invoice=persisted,
            created=created,
            changed=changed,
            lines_created=lines_created,
            lines_changed=lines_changed,
            lines_deactivated=stale_result.modified_count,
        )

    @classmethod
    async def _upsert_invoice(
        cls,
        invoice: IncomingInvoice,
    ) -> tuple[IncomingInvoice, bool, bool]:
        db: AsyncIOMotorDatabase = get_db_for_tenant(invoice.tenant_id)
        for _ in range(4):
            existing_doc = await db.incoming_invoices.find_one({"tenant_id": invoice.tenant_id, "provider_uuid": invoice.provider_uuid})
            if existing_doc is None:
                try:
                    await db.incoming_invoices.insert_one(_model_doc(invoice))
                    return invoice, True, True
                except DuplicateKeyError:
                    continue

            existing = IncomingInvoice.model_validate(existing_doc)
            desired = invoice.model_copy(
                update={
                    "id": existing.id,
                    "received_at": existing.received_at,
                    "created_at": existing.created_at,
                    "updated_at": existing.updated_at,
                    "version": existing.version,
                }
            )
            changes = cls._changed_fields(existing, desired, cls._INVOICE_MUTABLE_FIELDS)
            if not changes:
                return existing, False, False

            now = datetime.now(UTC)
            result = await db.incoming_invoices.update_one(
                {
                    "tenant_id": invoice.tenant_id,
                    "provider_uuid": invoice.provider_uuid,
                    "version": existing.version,
                },
                {
                    "$set": {**_mongo_value(changes), "updated_at": now},
                    "$inc": {"version": 1},
                },
            )
            if result.modified_count == 1:
                return desired.model_copy(update={"updated_at": now, "version": existing.version + 1}), False, True
        raise RuntimeError("INCOMING_INVOICE_UPSERT_CONFLICT")

    @classmethod
    async def _upsert_line(cls, line: IncomingInvoiceLine) -> tuple[bool, bool]:
        db: AsyncIOMotorDatabase = get_db_for_tenant(line.tenant_id)
        for _ in range(4):
            existing_doc = await db.incoming_invoice_lines.find_one(
                {
                    "tenant_id": line.tenant_id,
                    "incoming_invoice_id": line.incoming_invoice_id,
                    "line_number": line.line_number,
                }
            )
            if existing_doc is None:
                try:
                    await db.incoming_invoice_lines.insert_one(_model_doc(line))
                    return True, True
                except DuplicateKeyError:
                    continue

            existing = IncomingInvoiceLine.model_validate(existing_doc)
            changes = cls._changed_fields(existing, line, cls._LINE_MUTABLE_FIELDS)
            if not changes:
                return False, False

            result = await db.incoming_invoice_lines.update_one(
                {
                    "tenant_id": line.tenant_id,
                    "incoming_invoice_id": line.incoming_invoice_id,
                    "line_number": line.line_number,
                    "version": existing.version,
                },
                {
                    "$set": {**_mongo_value(changes), "updated_at": datetime.now(UTC)},
                    "$inc": {"version": 1},
                },
            )
            if result.modified_count == 1:
                return False, True
        raise RuntimeError("INCOMING_INVOICE_LINE_UPSERT_CONFLICT")

    @staticmethod
    def _changed_fields(existing, desired, field_names: tuple[str, ...]) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for field_name in field_names:
            old_value = _comparison_value(getattr(existing, field_name))
            new_value = _comparison_value(getattr(desired, field_name))
            if old_value != new_value:
                changes[field_name] = getattr(desired, field_name)
        return changes

    @staticmethod
    async def update_answer_status(
        tenant_id: str,
        invoice_id: str,
        new_status: IncomingInvoiceAnswerStatus,
    ) -> bool:
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
