"""Invoice sync indexes.

Revision ID: v002
Revises: v001
"""

from __future__ import annotations
import pymongo
from ..base import Migration

class InvoiceSyncIndexesMigration(Migration):
    version = "V002"
    description = "Create invoice sync uniqueness and retry indexes"

    async def up(self, db) -> None:
        # uq_invoice_sync_invoice_provider_kind: tenant_id + invoice_id + provider + document_kind (Unique)
        await db.invoice_sync.create_index(
            [
                ("tenant_id", pymongo.ASCENDING),
                ("invoice_id", pymongo.ASCENDING),
                ("provider", pymongo.ASCENDING),
                ("document_kind", pymongo.ASCENDING),
            ],
            unique=True,
            name="uq_invoice_sync_invoice_provider_kind"
        )

        # uq_invoice_sync_provider_request_uuid: provider + request_uuid (Unique)
        await db.invoice_sync.create_index(
            [
                ("provider", pymongo.ASCENDING),
                ("request_uuid", pymongo.ASCENDING),
            ],
            unique=True,
            name="uq_invoice_sync_provider_request_uuid"
        )

        # uq_invoice_sync_tenant_provider_idempotency: tenant_id + provider + idempotency_key (Unique)
        await db.invoice_sync.create_index(
            [
                ("tenant_id", pymongo.ASCENDING),
                ("provider", pymongo.ASCENDING),
                ("idempotency_key", pymongo.ASCENDING),
            ],
            unique=True,
            name="uq_invoice_sync_tenant_provider_idempotency"
        )

        # ix_invoice_sync_tenant_state_retry: tenant_id + state + next_retry_at
        await db.invoice_sync.create_index(
            [
                ("tenant_id", pymongo.ASCENDING),
                ("state", pymongo.ASCENDING),
                ("next_retry_at", pymongo.ASCENDING),
            ],
            name="ix_invoice_sync_tenant_state_retry"
        )

    async def down(self, db) -> None:
        indexes_to_drop = [
            "uq_invoice_sync_invoice_provider_kind",
            "uq_invoice_sync_provider_request_uuid",
            "uq_invoice_sync_tenant_provider_idempotency",
            "ix_invoice_sync_tenant_state_retry"
        ]
        for idx in indexes_to_drop:
            try:
                await db.invoice_sync.drop_index(idx)
            except Exception as exc:
                msg = str(exc).lower()
                if "index not found" in msg or "not found" in msg:
                    continue
                raise

MIGRATION = InvoiceSyncIndexesMigration()
