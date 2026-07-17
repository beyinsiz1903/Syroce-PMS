"""Invoice sync indexes.

Revision ID: v002
Revises: v001
"""

import pymongo

async def upgrade(db):
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

async def downgrade(db):
    await db.invoice_sync.drop_index("uq_invoice_sync_invoice_provider_kind")
    await db.invoice_sync.drop_index("uq_invoice_sync_provider_request_uuid")
    await db.invoice_sync.drop_index("uq_invoice_sync_tenant_provider_idempotency")
    await db.invoice_sync.drop_index("ix_invoice_sync_tenant_state_retry")
