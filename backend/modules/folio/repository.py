import hashlib
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.database import db
from core.utils import calculate_folio_balance


class FolioRepository:
    async def get_folio(self, tenant_id: str, folio_id: str) -> dict[str, Any] | None:
        return await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})

    async def get_booking_for_tenant(self, tenant_id: str, booking_id: str) -> dict[str, Any] | None:
        return await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})

    async def get_guest_for_tenant(self, tenant_id: str, guest_id: str) -> dict[str, Any] | None:
        return await db.guests.find_one({"id": guest_id, "tenant_id": tenant_id}, {"_id": 0})

    async def get_company_for_tenant(self, tenant_id: str, company_id: str) -> dict[str, Any] | None:
        return await db.companies.find_one({"id": company_id, "tenant_id": tenant_id}, {"_id": 0})

    async def get_open_folio_for_booking(
        self,
        tenant_id: str,
        booking_id: str,
        folio_type: str,
    ) -> dict[str, Any] | None:
        return await db.folios.find_one(
            {
                "tenant_id": tenant_id,
                "booking_id": booking_id,
                "folio_type": folio_type,
                "status": "open",
            },
            {"_id": 0},
        )

    async def insert_folio(self, folio_doc: dict[str, Any]) -> None:
        await db.folios.insert_one(folio_doc)

    async def insert_outbox_event(self, event_doc: dict[str, Any]) -> None:
        await db.outbox_events.insert_one(event_doc)

    async def get_charges(self, tenant_id: str, folio_id: str) -> list[dict[str, Any]]:
        return await db.folio_charges.find({"folio_id": folio_id, "tenant_id": tenant_id}, {"_id": 0}).to_list(1000)

    async def get_payments(self, tenant_id: str, folio_id: str) -> list[dict[str, Any]]:
        return await db.payments.find({"folio_id": folio_id, "tenant_id": tenant_id}, {"_id": 0}).to_list(1000)

    async def get_balance(self, tenant_id: str, folio_id: str) -> float:
        return await calculate_folio_balance(folio_id, tenant_id)

    async def acquire_idempotency_lock(
        self,
        tenant_id: str,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        from datetime import timedelta as _td

        from shared_kernel.idempotency import (
            IDEMPOTENCY_PROCESSING_GRACE_SECONDS,
            unseal_response_body,
        )
        lock_id = hashlib.sha256(f"{tenant_id}:{scope}:{idempotency_key}".encode()).hexdigest()
        now = datetime.now(UTC)
        lock_doc = {
            "_id": lock_id,
            "tenant_id": tenant_id,
            "scope": scope,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "correlation_id": correlation_id,
            "status": "processing",
            "created_at": now.isoformat(),
            # Task #81 — TTL sweep field; processing rows expire after grace.
            "expires_at": now + _td(seconds=IDEMPOTENCY_PROCESSING_GRACE_SECONDS),
        }
        try:
            await db.idempotency_keys.insert_one(lock_doc)
            lock_doc.pop("_id", None)
            return {"status": "acquired", "document": lock_doc, "lock_id": lock_id}
        except DuplicateKeyError:
            existing = await db.idempotency_keys.find_one({"_id": lock_id}, {"_id": 0})
            if existing is not None:
                # Surface a decrypted body so the service's existing
                # `existing["response_body"]` replay path stays unchanged.
                existing["response_body"] = unseal_response_body(existing)
            return {"status": "existing", "document": existing or {}, "lock_id": lock_id}

    async def complete_idempotency_lock(
        self,
        lock_id: str,
        folio_id: str,
        response_body: dict[str, Any],
    ) -> None:
        from datetime import timedelta as _td

        from shared_kernel.idempotency import (
            IDEMPOTENCY_RETENTION_SECONDS,
            seal_response_body,
        )
        now = datetime.now(UTC)
        await db.idempotency_keys.update_one(
            {"_id": lock_id},
            {
                "$set": {
                    "status": "completed",
                    "folio_id": folio_id,
                    # PII-at-rest: encrypted envelope only, never plaintext.
                    **seal_response_body(response_body),
                    "completed_at": now.isoformat(),
                    # Task #81 — extend TTL to retention window on completion.
                    "expires_at": now + _td(seconds=IDEMPOTENCY_RETENTION_SECONDS),
                }
            },
        )

    async def fail_idempotency_lock(self, lock_id: str, error_message: str) -> None:
        from datetime import timedelta as _td

        from shared_kernel.idempotency import IDEMPOTENCY_RETENTION_SECONDS
        now = datetime.now(UTC)
        await db.idempotency_keys.update_one(
            {"_id": lock_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": error_message,
                    "failed_at": now.isoformat(),
                    # Task #81 — failed rows are still kept for replay so a
                    # retry sees the failure verdict; expire at the same 24h
                    # mark as completed rows.
                    "expires_at": now + _td(seconds=IDEMPOTENCY_RETENTION_SECONDS),
                }
            },
        )
